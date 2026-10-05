"""World Bank Indicators API v2 adapter (no API key). https://api.worldbank.org/v2"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.base import DataProvider, IndicatorDef, Observation, ProviderError, SeriesResult

BASE_URL = "https://api.worldbank.org/v2"
COUNTRY_RE = re.compile(r"^[A-Za-z]{2,3}$")

# Registry: add indicators here — nothing else in LifeSpan hardcodes these codes except the
# economic engine's choice of which *kind* of series it needs.
INDICATORS: dict[str, IndicatorDef] = {
    "FP.CPI.TOTL": IndicatorDef("FP.CPI.TOTL", "Consumer price index (2010 = 100)", "index (2010 = 100)", "cpi-index"),
    "FP.CPI.TOTL.ZG": IndicatorDef("FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)", "% per year", "inflation-rate"),
    "PA.NUS.FCRF": IndicatorDef("PA.NUS.FCRF", "Official exchange rate (LCU per US$, period average)", "LCU per US$", "fx-lcu-per-usd",
                                "Annual period average — not a daily or spot rate."),
}


class WorldBankProvider(DataProvider):
    provider_id = "world-bank"
    provider_name = "World Bank"
    dataset = "World Development Indicators"
    authentication = "none"
    indicators = INDICATORS

    def __init__(self, transport: httpx.BaseTransport | None = None, timeout: float = 15.0):
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport, follow_redirects=True)

    def _get(self, path: str, params: dict) -> list:
        try:
            r = self._client.get(path, params={"format": "json", **params})
        except httpx.TimeoutException as e:
            raise ProviderError("timeout", "World Bank API timed out") from e
        except httpx.HTTPError as e:
            raise ProviderError("network", f"World Bank API unreachable: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise ProviderError("http", f"World Bank API returned HTTP {r.status_code}")
        try:
            data = r.json()
        except ValueError as e:
            raise ProviderError("malformed", "World Bank API returned non-JSON") from e
        if not isinstance(data, list) or not data:
            raise ProviderError("malformed", "Unexpected World Bank response shape")
        # Error payloads look like [{"message":[{"id":"120","key":"Invalid value","value":"..."}]}]
        if isinstance(data[0], dict) and "message" in data[0]:
            msgs = data[0]["message"]
            text = "; ".join(f"{x.get('key', '')}: {x.get('value', '')}".strip() for x in msgs if isinstance(x, dict)) or "error"
            raise ProviderError("invalid-request", f"World Bank: {text}")
        return data

    def fetch_metadata(self, indicator: str) -> dict:
        data = self._get(f"/indicator/{indicator}", {})
        rows = data[1] if len(data) > 1 and isinstance(data[1], list) else []
        if not rows or not isinstance(rows[0], dict):
            raise ProviderError("malformed", "Indicator metadata missing")
        row = rows[0]
        return {
            "name": row.get("name") or INDICATORS.get(indicator, IndicatorDef(indicator, indicator, "", "other")).name,
            "sourceNote": row.get("sourceNote") or "",
            "sourceOrganization": row.get("sourceOrganization") or "",
            "source": (row.get("source") or {}).get("value", ""),
        }

    def normalize(self, raw: dict, meta: dict) -> Observation | None:
        if not isinstance(raw, dict):
            raise ProviderError("malformed", "Observation row is not an object")
        try:
            year = int(raw["date"])
            ind = raw["indicator"]["id"]
            cc = raw.get("countryiso3code") or raw["country"]["id"]
        except (KeyError, TypeError, ValueError) as e:
            raise ProviderError("malformed", "Observation row missing date/indicator/country") from e
        v = raw.get("value")
        if v is None:
            return None  # provider has no value for that year — reported as missing, never invented
        try:
            value = Decimal(repr(v)) if isinstance(v, float) else Decimal(str(v))
        except InvalidOperation as e:
            raise ProviderError("malformed", f"Non-numeric value {v!r}") from e
        idef = INDICATORS.get(ind)
        return Observation(
            provider=self.provider_id, dataset=self.dataset, indicator_code=ind,
            indicator_name=raw["indicator"].get("value") or (idef.name if idef else ind),
            country_code=cc, country_name=(raw.get("country") or {}).get("value", cc), year=year, value=value,
            unit=idef.unit if idef else (raw.get("unit") or ""),
            source_organization=meta.get("sourceOrganization", ""), source_note=meta.get("sourceNote", ""),
            license="CC BY 4.0 (World Bank Open Data terms)",
            source_url=f"{BASE_URL}/country/{cc}/indicator/{ind}?date={year}&format=json",
            provider_last_updated=meta.get("lastUpdated", ""),
            raw={k: raw.get(k) for k in ("indicator", "country", "countryiso3code", "date", "value", "unit", "obs_status", "decimal")},
        )

    def fetch_series(self, indicator: str, countries: list[str], year_start: int, year_end: int) -> SeriesResult:
        if not countries:
            raise ProviderError("invalid-request", "No countries requested")
        bad = [c for c in countries if not COUNTRY_RE.match(c)]
        if bad:
            raise ProviderError("invalid-request", f"Invalid country code(s): {', '.join(bad)}")
        if year_end < year_start:
            raise ProviderError("invalid-request", "yearEnd must be >= yearStart")
        try:
            meta = self.fetch_metadata(indicator)
        except ProviderError as e:
            if e.kind in ("timeout", "network"):
                raise
            meta = {}
        obs: list[Observation] = []
        missing: list[dict] = []
        seen: set[tuple[str, int]] = set()
        unknown: list[str] = []
        for cc in countries:
            try:
                data = self._get(f"/country/{cc}/indicator/{indicator}", {"date": f"{year_start}:{year_end}", "per_page": 1000})
            except ProviderError as e:
                if e.kind == "invalid-request":
                    unknown.append(cc.upper())
                    continue
                raise
            header = data[0] if isinstance(data[0], dict) else {}
            rows = data[1] if len(data) > 1 and isinstance(data[1], list) else []
            meta_c = {**meta, "lastUpdated": header.get("lastupdated", "")}
            got: set[int] = set()
            iso = None
            for raw in rows:
                o = self.normalize(raw, meta_c)
                yr = int(raw.get("date", 0)) if str(raw.get("date", "")).isdigit() else None
                iso = iso or (o.country_code if o else raw.get("countryiso3code"))
                if o is None:
                    if yr is not None:
                        missing.append({"country": cc.upper(), "year": yr, "reason": "no value published"})
                        got.add(yr)
                    continue
                if (o.country_code, o.year) in seen:
                    continue
                seen.add((o.country_code, o.year))
                got.add(o.year)
                obs.append(o)
            for yr in range(year_start, year_end + 1):
                if yr not in got:
                    missing.append({"country": cc.upper(), "year": yr, "reason": "not in provider response"})
        return SeriesResult(observations=obs, missing=sorted(missing, key=lambda x: (x["country"], x["year"])), countries_unknown=unknown)

    def ping(self) -> tuple[bool, str]:
        try:
            self._get("/indicator/FP.CPI.TOTL", {})
            return True, "reachable"
        except ProviderError as e:
            return False, e.kind
