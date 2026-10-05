"""Provider abstraction. The rest of LifeSpan depends only on this module, never on a
specific provider's wire format."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


class ProviderError(Exception):
    """Provider could not answer (network, timeout, HTTP error, malformed payload)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind  # network | timeout | http | malformed | invalid-request | disabled


@dataclass(frozen=True)
class IndicatorDef:
    code: str
    name: str
    unit: str
    kind: str  # cpi-index | inflation-rate | fx-lcu-per-usd | other
    precision_note: str = ""


@dataclass
class Observation:
    """Normalised value exactly as retrieved. `value` keeps full provider precision as Decimal."""
    provider: str
    dataset: str
    indicator_code: str
    indicator_name: str
    country_code: str
    country_name: str
    year: int
    value: Decimal
    unit: str
    source_organization: str = ""
    source_note: str = ""
    license: str = ""
    source_url: str = ""
    provider_last_updated: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class SeriesResult:
    observations: list[Observation]
    missing: list[dict]  # [{country, year, reason}] — never filled with invented values
    countries_unknown: list[str] = field(default_factory=list)


class DataProvider:
    provider_id: str = ""
    provider_name: str = ""
    dataset: str = ""
    authentication: str = "none"
    indicators: dict[str, IndicatorDef] = {}

    def fetch_series(self, indicator: str, countries: list[str], year_start: int, year_end: int) -> SeriesResult:
        raise NotImplementedError

    def fetch_metadata(self, indicator: str) -> dict:
        raise NotImplementedError

    def normalize(self, raw: dict, meta: dict) -> Observation | None:
        raise NotImplementedError

    def describe(self) -> dict:
        return {
            "id": self.provider_id, "name": self.provider_name, "dataset": self.dataset, "authentication": self.authentication,
            "indicators": [{"code": i.code, "name": i.name, "unit": i.unit, "kind": i.kind, "precisionNote": i.precision_note} for i in self.indicators.values()],
        }
