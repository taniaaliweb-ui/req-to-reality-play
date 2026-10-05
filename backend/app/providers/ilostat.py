"""ILOSTAT provider — official ILO SDMX REST web service (free, no API key).
https://sdmx.ilo.org/rest/data/ILO,<DATAFLOW>,1.0/<KEY>?startPeriod=..&endPeriod=..&format=csvfilewithlabels
Never scrapes the ILOSTAT website."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from app.providers.base import DataProvider, IndicatorDef, Observation, ProviderError, SeriesResult
from app.providers.sdmx import SdmxRecord, parse_csv

BASE_URL = "https://sdmx.ilo.org/rest"
COUNTRY_RE = re.compile(r"^[A-Za-z]{3}$")
CURRENCY_NOTE = re.compile(r"\b([A-Z]{3}): [A-Z][a-z]")


@dataclass(frozen=True)
class LaborIndicator:
    dataflow: str
    name: str
    concept: str  # earnings | context
    statistic: str  # MEAN | MEDIAN | RATE
    pay_period: str | None  # MONTHLY | HOURLY | None
    dims: tuple[str, ...]  # classification dimensions after REF_AREA, FREQ, MEASURE

    @property
    def key_len(self) -> int:
        return 3 + len(self.dims)


# Registry — add dataflows here; nothing else hardcodes ILO codes.
REGISTRY: dict[str, LaborIndicator] = {i.dataflow: i for i in [
    LaborIndicator("DF_EAR_EMTA_SEX_OCU_NB", "Average monthly earnings of employees by sex and occupation", "earnings", "MEAN", "MONTHLY", ("SEX", "OCU")),
    LaborIndicator("DF_EAR_EMTM_SEX_OCU_NB", "Median monthly earnings of employees by sex and occupation", "earnings", "MEDIAN", "MONTHLY", ("SEX", "OCU")),
    LaborIndicator("DF_EAR_EMTM_SEX_NB", "Median monthly earnings of employees by sex", "earnings", "MEDIAN", "MONTHLY", ("SEX",)),
    LaborIndicator("DF_EAR_EMTA_SEX_EDU_NB", "Average monthly earnings of employees by sex and education", "earnings", "MEAN", "MONTHLY", ("SEX", "EDU")),
    LaborIndicator("DF_EAR_EMTA_SEX_GEO_NB", "Average monthly earnings of employees by sex and rural/urban areas", "earnings", "MEAN", "MONTHLY", ("SEX", "GEO")),
    LaborIndicator("DF_EAR_EMTA_SEX_ECO_NB", "Average monthly earnings of employees by sex and economic activity", "earnings", "MEAN", "MONTHLY", ("SEX", "ECO")),
    LaborIndicator("DF_EAR_EHRA_SEX_NB", "Average hourly earnings of employees by sex", "earnings", "MEAN", "HOURLY", ("SEX",)),
    LaborIndicator("DF_EAP_DWAP_SEX_AGE_RT", "Labour force participation rate by sex and age", "context", "RATE", None, ("SEX", "AGE")),
    LaborIndicator("DF_EMP_DWAP_SEX_AGE_RT", "Employment-to-population ratio by sex and age", "context", "RATE", None, ("SEX", "AGE")),
    LaborIndicator("DF_UNE_DEAP_SEX_AGE_RT", "Unemployment rate by sex and age", "context", "RATE", None, ("SEX", "AGE")),
]}
# Informal employment and status-in-employment series exist in ILOSTAT but are not registered yet.


def currency_of(rec: SdmxRecord) -> str | None:
    if rec.attrs.get("UNIT_MEASURE") not in ("LC", "LCU"):
        return None if rec.attrs.get("UNIT_MEASURE") else None
    for k in ("NOTE_CLASSIF", "NOTE_INDICATOR", "NOTE_SOURCE"):
        m = CURRENCY_NOTE.search(rec.attrs.get(k, ""))
        if m:
            return m.group(1)
    return None


class ILOStatProvider(DataProvider):
    provider_id = "ilostat"
    provider_name = "ILOSTAT (International Labour Organization)"
    dataset = "ILOSTAT SDMX"
    authentication = "none"
    indicators = {k: IndicatorDef(k, v.name, v.pay_period or "%", v.concept) for k, v in REGISTRY.items()}

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 60.0):
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport, follow_redirects=True,
                                    headers={"User-Agent": "LifeSpan/0.4 (local research app)"})

    def _get(self, path: str, attempts: int = 3) -> httpx.Response:
        r = None
        for attempt in range(attempts):
            try:
                r = self._client.get(path)
            except httpx.TimeoutException as e:
                if attempt == attempts - 1:
                    raise ProviderError("timeout", "ILOSTAT timed out") from e
                time.sleep(1.0 * (attempt + 1))
                continue
            except httpx.HTTPError as e:
                raise ProviderError("network", f"ILOSTAT unreachable: {type(e).__name__}") from e
            if r.status_code == 429:
                raise ProviderError("rate-limit", "ILOSTAT rate limit reached — try again later")
            if r.status_code < 500 or attempt == attempts - 1:
                break
            time.sleep(1.0 * (attempt + 1))
        assert r is not None
        return r

    def normalize(self, rec: SdmxRecord, meta: dict | None = None) -> Observation | None:
        if rec.value is None or rec.year is None:
            return None
        ind = REGISTRY.get(rec.dataflow)
        cur = currency_of(rec)
        unit = (f"{cur} per {'month' if ind and ind.pay_period == 'MONTHLY' else 'hour'}" if cur and ind and ind.pay_period
                else rec.attrs.get("UNIT_MEASURE_LABEL") or rec.attrs.get("UNIT_MEASURE", ""))
        dims_txt = ", ".join(f"{k}: {d['label'] or d['code']}" for k, d in rec.dims.items())
        return Observation(
            provider=self.provider_id, dataset=f"ILOSTAT {rec.dataflow}", indicator_code=rec.dataflow,
            indicator_name=f"{rec.measure_label or rec.measure} ({dims_txt})", country_code=rec.ref_area, country_name=rec.ref_area_label or rec.ref_area,
            year=rec.year, value=rec.value, unit=unit, source_organization="International Labour Organization (ILOSTAT)",
            source_note=" | ".join(x for x in (rec.attrs.get("SOURCE", ""), rec.attrs.get("NOTE_SOURCE", ""), rec.attrs.get("NOTE_INDICATOR", ""), rec.attrs.get("NOTE_CLASSIF", "")) if x),
            license="ILOSTAT terms of use (free, attribution)",
            source_url=f"{BASE_URL}/data/ILO,{rec.dataflow},1.0/{rec.ref_area}{'.' * (ind.key_len - 1) if ind else ''}?format=csvfilewithlabels",
            raw={"dataflow": rec.dataflow, "dataflowName": rec.dataflow_name, "period": rec.period, "freq": rec.freq, "measure": rec.measure,
                 "measureLabel": rec.measure_label, "dims": rec.dims, "attrs": rec.attrs, "currency": cur, "concept": ind.concept if ind else None,
                 "statistic": ind.statistic if ind else None, "payPeriod": ind.pay_period if ind else None},
            obs_key=f"ilostat:{rec.dataflow}:{rec.ref_area}:{rec.dim_key}:{rec.period}",
        )

    def fetch_series(self, indicator: str, countries: list[str], year_start: int, year_end: int, *, annual_only: bool = True) -> SeriesResult:
        ind = REGISTRY.get(indicator)
        if ind is None:
            raise ProviderError("invalid-request", f"Unknown ILOSTAT dataflow {indicator}")
        cs = [c.upper() for c in countries]
        bad = [c for c in cs if not COUNTRY_RE.match(c)]
        if not cs or bad:
            raise ProviderError("invalid-request", "ILOSTAT needs ISO3 country codes" + (f" (invalid: {', '.join(bad)})" if bad else ""))
        if year_end < year_start:
            raise ProviderError("invalid-request", "yearEnd must be >= yearStart")
        key = "+".join(cs) + "." * (ind.key_len - 1)
        r = self._get(f"/data/ILO,{indicator},1.0/{key}?startPeriod={year_start}&endPeriod={year_end}&format=csvfilewithlabels")
        if r.status_code == 404:
            recs: list[SdmxRecord] = []  # SDMX "no results" — reported below as missing
        elif r.status_code >= 400:
            raise ProviderError("http", f"ILOSTAT returned HTTP {r.status_code}: {r.text[:160]}")
        else:
            if "<html" in r.text[:300].lower():
                raise ProviderError("malformed", "ILOSTAT returned an HTML page instead of data (possibly blocked)")
            recs = parse_csv(r.text)
        obs: list[Observation] = []
        missing: list[dict] = []
        got: set[tuple[str, int]] = set()
        skipped = 0
        for rec in recs:
            if annual_only and rec.freq and rec.freq != "A":
                skipped += 1
                continue
            o = self.normalize(rec)
            if o is None:
                if rec.year:
                    missing.append({"country": rec.ref_area, "year": rec.year, "reason": f"null value ({rec.dim_key})"})
                continue
            got.add((o.country_code, o.year))
            obs.append(o)
        for c in cs:
            for y in range(year_start, year_end + 1):
                if (c, y) not in got:
                    missing.append({"country": c, "year": y, "reason": "no observation published"})
        res = SeriesResult(observations=obs, missing=sorted(missing, key=lambda x: (x["country"], x["year"])),
                           countries_unknown=[c for c in cs if not any(o.country_code == c for o in obs)])
        res.skipped_subannual = skipped  # type: ignore[attr-defined]
        return res

    def ping(self) -> tuple[bool, str]:
        try:
            r = self._get("/dataflow/ILO/DF_EAR_EMTM_SEX_NB/latest", attempts=1)
            return (r.status_code == 200, "reachable" if r.status_code == 200 else f"http {r.status_code}")
        except ProviderError as e:
            return False, e.kind

    def describe(self) -> dict:
        d = super().describe()
        d["indicators"] = [{"code": i.dataflow, "name": i.name, "unit": i.pay_period or "rate", "kind": i.concept, "precisionNote": i.statistic,
                            "dims": list(i.dims)} for i in REGISTRY.values()]
        d["mode"] = "LIVE_API"
        return d
