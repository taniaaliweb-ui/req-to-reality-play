"""UN World Population Prospects 2024 — ABRIDGED LIFE TABLES (official, free, no key).

Age-specific probability of dying nqx for age groups 0, 1–4, 5–9 … 95–99 and the open group 100+
(with its central death rate mx), by country, single calendar year and sex (Male / Female / Both sexes).
Two official bulk files: estimates 1950–2023 and Medium-variant projections 2024–2100. Each is downloaded
once (~145 MB gzip) and cached under the data directory; only the requested countries are kept.

Values are stored exactly as published (no smoothing or interpolation). The simulation converts an
n-year probability to an annual one with a documented, versioned formula (see simulation/rules/mortality.py)."""
from __future__ import annotations

import csv
import gzip
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

from app.providers.base import Observation, ProviderError, SeriesResult

WPP_EDITION = "WPP2024"
BASE = "https://population.un.org/wpp/assets/Excel%20Files/1_Indicator%20(Standard)/CSV_FILES/"
FILES = {"estimates": ("WPP2024_Life_Table_Abridged_Medium_1950-2023.csv.gz", 1950, 2023),
         "projections": ("WPP2024_Life_Table_Abridged_Medium_2024-2100.csv.gz", 2024, 2100)}
SOURCE_PAGE = "https://population.un.org/wpp/downloads"
ORG = "United Nations, Department of Economic and Social Affairs, Population Division"
LICENSE = "CC BY 3.0 IGO"
LAST_ESTIMATE_YEAR = 2023
SEX = {"Male": "MALE", "Female": "FEMALE", "Total": "BOTH", "Both sexes": "BOTH"}


class UNWPPLifeTableProvider:
    provider_id = "un-wpp-lt"
    provider_name = "UN World Population Prospects — abridged life tables"
    dataset = f"{WPP_EDITION} Abridged Life Table (Medium variant)"
    authentication = "none (official bulk CSV)"

    def __init__(self, cache_dir: Path, fixture_dir: str | None = None, timeout: float = 300.0):
        self.dir = Path(fixture_dir) if fixture_dir else cache_dir
        self.fixture = bool(fixture_dir)
        self.timeout = timeout

    def path(self, kind: str) -> Path:
        return self.dir / FILES[kind][0]

    def cached(self, kind: str) -> bool:
        p = self.path(kind)
        return p.exists() and p.stat().st_size > 0

    def download(self, kind: str) -> None:
        if self.fixture:
            return
        p = self.path(kind)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        try:
            with httpx.stream("GET", BASE + FILES[kind][0], timeout=self.timeout, follow_redirects=True, headers={"User-Agent": "LifeSpan/0.6"}) as r:
                if r.status_code != 200:
                    raise ProviderError("http", f"UN WPP life table download returned HTTP {r.status_code}")
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
        except httpx.TimeoutException as e:
            raise ProviderError("timeout", "UN WPP life table download timed out") from e
        except httpx.HTTPError as e:
            raise ProviderError("network", f"UN WPP unreachable: {type(e).__name__}") from e
        try:
            with gzip.open(tmp, "rt", encoding="utf-8-sig") as fh:
                header = fh.readline()
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise ProviderError("malformed", "UN WPP life table is not a gzip CSV") from e
        if "qx" not in header or "AgeGrpStart" not in header:
            tmp.unlink(missing_ok=True)
            raise ProviderError("malformed", "UN WPP life table header not recognised")
        os.replace(tmp, p)

    def ping(self) -> tuple[bool, str]:
        try:
            r = httpx.head(BASE + FILES["estimates"][0], timeout=15, follow_redirects=True, headers={"User-Agent": "LifeSpan/0.6"})
        except httpx.HTTPError:
            return False, "network"
        return (True, "bulk file reachable") if r.status_code == 200 else (False, f"http {r.status_code}")

    def fetch(self, countries: list[str], year_start: int, year_end: int, sexes: list[str] | None = None) -> SeriesResult:
        want = {c.upper() for c in countries}
        sx_want = set(sexes or ["MALE", "FEMALE", "BOTH"])
        obs: list[Observation] = []
        seen: set[str] = set()
        missing: list[dict] = []
        for kind, (fname, y0, y1) in FILES.items():
            if year_end < y0 or year_start > y1:
                continue
            if not self.cached(kind):
                self.download(kind)
            if not self.cached(kind):
                missing.append({"file": fname, "reason": "file not available"})
                continue
            with gzip.open(self.path(kind), "rt", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    iso3 = (row.get("ISO3_code") or "").upper()
                    if iso3 not in want:
                        continue
                    try:
                        y = int(row["Time"])
                    except (KeyError, ValueError):
                        continue
                    sex = SEX.get(row.get("Sex") or "")
                    if not (year_start <= y <= year_end) or sex not in sx_want:
                        continue
                    seen.add(iso3)
                    o = self.normalize(row, iso3, y, sex)
                    if o is None:
                        missing.append({"country": iso3, "year": y, "sex": sex, "ageGroup": row.get("AgeGrp"), "reason": "no qx published"})
                    else:
                        obs.extend(o)
        return SeriesResult(observations=obs, missing=missing, countries_unknown=sorted(want - seen))

    def normalize(self, row: dict, iso3: str, year: int, sex: str) -> list[Observation] | None:
        try:
            qx = Decimal((row.get("qx") or "").strip())
        except InvalidOperation:
            return None
        start = int(row["AgeGrpStart"])
        span = int(row["AgeGrpSpan"])
        label = row.get("AgeGrp") or str(start)
        projection = year > LAST_ESTIMATE_YEAR
        note = ("PROJECTION (WPP Medium variant) — not an observed value." if projection else f"{WPP_EDITION} estimate.")
        base = dict(provider=self.provider_id, dataset=self.dataset, country_code=iso3, country_name=row.get("Location", iso3), year=year,
                    source_organization=ORG, source_note=note, license=LICENSE, source_url=SOURCE_PAGE, provider_last_updated=WPP_EDITION)
        raw = {"LocID": row.get("LocID"), "ISO3_code": iso3, "Time": row.get("Time"), "Sex": row.get("Sex"), "AgeGrp": label, "ageStart": start,
               "ageSpan": span, "qx": row.get("qx"), "mx": row.get("mx"), "projection": projection, "domain": "mortality", "sex": None if sex == "BOTH" else sex,
               "sexLabel": sex, "age": str(start), "ageGroup": label, "file": FILES["projections" if projection else "estimates"][0]}
        out = [Observation(indicator_code="LT_QX", indicator_name=f"Probability of dying {label} (nqx)", value=qx, unit="probability (0–1) over the age interval",
                           raw=raw, obs_key=f"{self.provider_id}:QX:{iso3}:{sex}:{start}:{year}", **base)]
        if span < 0:  # open age group: central death rate is needed for an annual probability
            try:
                mx = Decimal((row.get("mx") or "").strip())
                out.append(Observation(indicator_code="LT_MX", indicator_name=f"Central death rate {label} (mx)", value=mx, unit="deaths per person-year",
                                       raw=raw, obs_key=f"{self.provider_id}:MX:{iso3}:{sex}:{start}:{year}", **base))
            except InvalidOperation:
                pass
        return out
