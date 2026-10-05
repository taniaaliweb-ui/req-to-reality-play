"""UN World Population Prospects (UN DESA Population Division) — official free bulk CSV.

The WPP Data Portal API requires a registered bearer token for data requests (verified: HTTP 401
without one), so LifeSpan uses the official, freely downloadable "Demographic Indicators" CSV
file instead. The file is downloaded once by the backend and cached under the data directory so
the app keeps working offline. No visualisation-site scraping.

Values are kept exactly as published (populations / births / deaths / migrants are in THOUSANDS).
Years after WPP's last estimate year are labelled PROJECTION, never presented as observed."""
from __future__ import annotations

import csv
import gzip
import io
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.providers.base import DataProvider, IndicatorDef, Observation, ProviderError, SeriesResult

WPP_EDITION = "WPP2024"
LAST_ESTIMATE_YEAR = 2023  # WPP 2024: estimates 1950–2023, projections 2024–2100
FILE_NAME = "WPP2024_Demographic_Indicators_Medium.csv.gz"
DOWNLOAD_URL = "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/" + FILE_NAME
SOURCE_PAGE = "https://population.un.org/wpp/downloads"
LICENSE = "CC BY 3.0 IGO (United Nations)"
ORG = "United Nations, Department of Economic and Social Affairs, Population Division"


@dataclass(frozen=True)
class WppMetric:
    column: str
    name: str
    unit: str
    domain: str  # demographic | mortality | fertility | migration
    sex: str | None = None  # MALE | FEMALE | None (= both sexes / not split)
    age: str | None = None  # age group the measure refers to, only when the definition fixes one


METRICS: dict[str, WppMetric] = {m.column: m for m in [
    WppMetric("TPopulation1July", "Total population, as of 1 July", "thousand persons", "demographic"),
    WppMetric("TPopulationMale1July", "Male population, as of 1 July", "thousand persons", "demographic", "MALE"),
    WppMetric("TPopulationFemale1July", "Female population, as of 1 July", "thousand persons", "demographic", "FEMALE"),
    WppMetric("MedianAgePop", "Median age of population", "years", "demographic"),
    WppMetric("PopGrowthRate", "Population growth rate", "% per year", "demographic"),
    WppMetric("Births", "Births", "thousand births", "fertility"),
    WppMetric("CBR", "Crude birth rate", "births per 1,000 population", "fertility"),
    WppMetric("TFR", "Total fertility rate", "live births per woman", "fertility", "FEMALE", "15-49"),
    WppMetric("MAC", "Mean age of childbearing", "years", "fertility", "FEMALE", "15-49"),
    WppMetric("Births1519", "Births by women aged 15 to 19", "thousand births", "fertility", "FEMALE", "15-19"),
    WppMetric("CDR", "Crude death rate", "deaths per 1,000 population", "mortality"),
    WppMetric("LEx", "Life expectancy at birth, both sexes", "years", "mortality", None, "0"),
    WppMetric("LExMale", "Male life expectancy at birth", "years", "mortality", "MALE", "0"),
    WppMetric("LExFemale", "Female life expectancy at birth", "years", "mortality", "FEMALE", "0"),
    WppMetric("LE15Male", "Male life expectancy at age 15", "years", "mortality", "MALE", "15"),
    WppMetric("LE65Male", "Male life expectancy at age 65", "years", "mortality", "MALE", "65"),
    WppMetric("LE65Female", "Female life expectancy at age 65", "years", "mortality", "FEMALE", "65"),
    WppMetric("IMR", "Infant mortality rate", "infant deaths per 1,000 live births", "mortality", None, "0"),
    WppMetric("Q5", "Under-five mortality", "deaths under age 5 per 1,000 live births", "mortality", None, "0-4"),
    WppMetric("Q1560Male", "Male mortality between age 15 and 60", "deaths per 1,000 males alive at age 15", "mortality", "MALE", "15-59"),
    WppMetric("Q1560Female", "Female mortality between age 15 and 60", "deaths per 1,000 females alive at age 15", "mortality", "FEMALE", "15-59"),
    WppMetric("NetMigrations", "Net number of migrants", "thousand persons", "migration"),
    WppMetric("CNMR", "Net migration rate", "per 1,000 population", "migration"),
]}


class UNWPPProvider(DataProvider):
    provider_id = "un-wpp"
    provider_name = "UN World Population Prospects"
    dataset = f"{WPP_EDITION} Demographic Indicators (Medium variant)"
    authentication = "none (official bulk CSV)"
    indicators = {k: IndicatorDef(k, v.name, v.unit, "other") for k, v in METRICS.items()}

    def __init__(self, cache_dir: Path, fixture_file: str | None = None, timeout: float = 120.0):
        self.cache_file = Path(fixture_file) if fixture_file else cache_dir / FILE_NAME
        self.fixture = bool(fixture_file)
        self.timeout = timeout

    # ---------------------------------------------------------------- file handling
    def cached(self) -> bool:
        return self.cache_file.exists() and self.cache_file.stat().st_size > 0

    def download(self) -> None:
        if self.fixture:
            return
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_file.with_suffix(".part")
        try:
            with httpx.stream("GET", DOWNLOAD_URL, timeout=self.timeout, follow_redirects=True, headers={"User-Agent": "LifeSpan/0.5"}) as r:
                if r.status_code != 200:
                    raise ProviderError("http", f"UN WPP download returned HTTP {r.status_code}")
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
        except httpx.TimeoutException as e:
            raise ProviderError("timeout", "UN WPP download timed out") from e
        except httpx.HTTPError as e:
            raise ProviderError("network", f"UN WPP unreachable: {type(e).__name__}") from e
        try:
            with gzip.open(tmp, "rt", encoding="utf-8-sig") as fh:
                header = fh.readline()
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise ProviderError("malformed", "UN WPP download is not a gzip CSV") from e
        if "ISO3_code" not in header or "TFR" not in header:
            tmp.unlink(missing_ok=True)
            raise ProviderError("malformed", "UN WPP CSV header not recognised")
        os.replace(tmp, self.cache_file)

    def ping(self) -> tuple[bool, str]:
        try:
            r = httpx.head(DOWNLOAD_URL, timeout=15, follow_redirects=True, headers={"User-Agent": "LifeSpan/0.5"})
        except httpx.TimeoutException:
            return False, "timeout"
        except httpx.HTTPError:
            return False, "network"
        return (True, "bulk file reachable") if r.status_code == 200 else (False, f"http {r.status_code}")

    def _rows(self):
        if not self.cached():
            self.download()
        if not self.cached():
            raise ProviderError("network", "UN WPP file not available")
        try:
            with gzip.open(self.cache_file, "rt", encoding="utf-8-sig", newline="") as fh:
                yield from csv.DictReader(fh)
        except (OSError, csv.Error) as e:
            raise ProviderError("malformed", f"UN WPP file unreadable: {e}") from e

    # ---------------------------------------------------------------- DataProvider
    def fetch_metadata(self, indicator: str) -> dict:
        mt = METRICS.get(indicator)
        if mt is None:
            raise ProviderError("invalid-request", f"Unknown WPP indicator {indicator}")
        return {"name": mt.name, "unit": mt.unit, "sourceOrganization": ORG, "source": self.dataset}

    def normalize(self, raw: dict, meta: dict) -> Observation | None:
        col = meta["column"]
        txt = (raw.get(col) or "").strip()
        if txt == "":
            return None
        try:
            value = Decimal(txt)
        except InvalidOperation:
            return None
        mt = METRICS[col]
        year = int(raw["Time"])
        iso3 = raw["ISO3_code"].upper()
        projection = year > LAST_ESTIMATE_YEAR
        return Observation(
            provider=self.provider_id, dataset=self.dataset, indicator_code=col, indicator_name=mt.name, country_code=iso3,
            country_name=raw.get("Location", iso3), year=year, value=value, unit=mt.unit, source_organization=ORG,
            source_note=("PROJECTION (WPP Medium variant) — not an observed value." if projection else f"{WPP_EDITION} estimate.") + (" " + raw.get("Notes", "") if raw.get("Notes") else ""),
            license=LICENSE, source_url=SOURCE_PAGE, provider_last_updated=WPP_EDITION,
            raw={"LocID": raw.get("LocID"), "ISO3_code": iso3, "ISO2_code": raw.get("ISO2_code"), "Variant": raw.get("Variant"), "Time": raw.get("Time"),
                 "column": col, "value": txt, "projection": projection, "domain": mt.domain, "sex": mt.sex, "age": mt.age, "file": FILE_NAME},
            obs_key=f"{self.provider_id}:{col}:{iso3}:{year}")

    def fetch_series(self, indicator: str, countries: list[str], year_start: int, year_end: int) -> SeriesResult:
        return self.fetch_many([indicator], countries, year_start, year_end)

    def fetch_many(self, indicators: list[str], countries: list[str], year_start: int, year_end: int) -> SeriesResult:
        unknown_ind = [i for i in indicators if i not in METRICS]
        if unknown_ind:
            raise ProviderError("invalid-request", f"Unknown WPP indicator(s): {', '.join(unknown_ind)}")
        want = {c.upper() for c in countries}
        seen_c: set[str] = set()
        obs: list[Observation] = []
        missing: list[dict] = []
        for row in self._rows():
            iso3 = (row.get("ISO3_code") or "").upper()
            if iso3 not in want or (row.get("LocTypeName") or "") != "Country/Area":
                continue
            try:
                y = int(row["Time"])
            except (KeyError, ValueError):
                continue
            if not (year_start <= y <= year_end):
                continue
            seen_c.add(iso3)
            for col in indicators:
                o = self.normalize(row, {"column": col})
                if o is None:
                    missing.append({"country": iso3, "year": y, "indicator": col, "reason": "no value published"})
                else:
                    obs.append(o)
        return SeriesResult(observations=obs, missing=missing, countries_unknown=sorted(want - seen_c))


def read_bytes_header(data: bytes) -> str:
    """Helper for tests: first line of a gzip CSV."""
    with gzip.open(io.BytesIO(data), "rt", encoding="utf-8-sig") as fh:
        return fh.readline()
