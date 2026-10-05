"""Manual / imported provider: values a person transcribed from an identified source.
Requires the source to be named; it never fabricates anything."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.providers.base import DataProvider, IndicatorDef, Observation, ProviderError


class ManualProvider(DataProvider):
    provider_id = "manual"
    provider_name = "Manual / imported dataset"
    dataset = "User-supplied"
    authentication = "none"
    indicators: dict[str, IndicatorDef] = {}

    def normalize(self, raw: dict, meta: dict | None = None) -> Observation:
        for k in ("indicatorCode", "countryCode", "year", "value", "unit", "sourceOrganization", "dataset"):
            if raw.get(k) in (None, ""):
                raise ProviderError("invalid-request", f"Manual observation needs '{k}'")
        try:
            value = Decimal(str(raw["value"]))
        except InvalidOperation as e:
            raise ProviderError("invalid-request", "value must be numeric") from e
        return Observation(
            provider=self.provider_id, dataset=str(raw["dataset"]), indicator_code=str(raw["indicatorCode"]),
            indicator_name=str(raw.get("indicatorName") or raw["indicatorCode"]), country_code=str(raw["countryCode"]).upper(),
            country_name=str(raw.get("countryName") or raw["countryCode"]), year=int(raw["year"]), value=value, unit=str(raw["unit"]),
            source_organization=str(raw["sourceOrganization"]), source_note=str(raw.get("sourceNote") or ""),
            source_url=str(raw.get("sourceUrl") or ""), raw=dict(raw),
        )
