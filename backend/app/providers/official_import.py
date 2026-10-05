"""Official-statistics providers that LifeSpan can only use via structured file import today.

* UAE FCSC (.Stat / SDMX): the documented service at uaestat.fcsc.gov.ae is checked live; until a
  data request has been verified end-to-end, LifeSpan imports SDMX-CSV or CSV files the user
  downloaded from it. No HTML scraping.
* India MoSPI (PLFS): no stable documented machine-readable endpoint has been verified, so only
  structured CSV import of published tables is offered. No PDF/HTML scraping."""
from __future__ import annotations

import httpx

from app.providers.base import DataProvider


class ImportOnlyProvider(DataProvider):
    mode = "AVAILABLE_IMPORT"
    ping_url: str | None = None

    def ping(self) -> tuple[bool, str]:
        if not self.ping_url:
            return False, "no live API"
        try:
            r = httpx.get(self.ping_url, timeout=10, headers={"User-Agent": "LifeSpan/0.4"}, follow_redirects=True)
        except httpx.TimeoutException:
            return False, "timeout"
        except httpx.HTTPError:
            return False, "network"
        if r.status_code == 200 and "<html" not in r.text[:300].lower():
            return True, "reachable"
        return False, f"http {r.status_code}" + (" (blocked page)" if "<html" in r.text[:300].lower() else "")

    def describe(self) -> dict:
        return {**super().describe(), "mode": self.mode}


class UAEStatProvider(ImportOnlyProvider):
    provider_id = "uae-fcsc"
    provider_name = "UAE Official Statistics (FCSC)"
    dataset = "UAE .Stat — Labour Force (import)"
    ping_url = "https://uaestat.fcsc.gov.ae/rest/dataflow/all/all/latest"


class IndiaMoSPIProvider(ImportOnlyProvider):
    provider_id = "india-mospi"
    provider_name = "India MoSPI (PLFS)"
    dataset = "Periodic Labour Force Survey (import)"
    ping_url = None
