"""Provider registry. Tests replace providers with recorded-response transports via env vars."""
from __future__ import annotations

import os

from app.providers.ilostat import ILOStatProvider
from app.providers.manual import ManualProvider
from app.providers.official_import import IndiaMoSPIProvider, UAEStatProvider
from app.providers.un_wpp import UNWPPProvider
from app.providers.un_wpp_lifetable import UNWPPLifeTableProvider
from app.providers.world_bank import WorldBankProvider


def get_world_bank() -> WorldBankProvider:
    # LIFESPAN_WB_FIXTURE_DIR lets automated tests run the real server against recorded responses.
    fixture_dir = os.environ.get("LIFESPAN_WB_FIXTURE_DIR")
    if fixture_dir:
        from app.providers.fixtures import fixture_transport
        return WorldBankProvider(transport=fixture_transport(fixture_dir))
    return WorldBankProvider()


def get_ilostat() -> ILOStatProvider:
    fixture_dir = os.environ.get("LIFESPAN_ILO_FIXTURE_DIR")
    if fixture_dir:
        from app.providers.fixtures import ilo_fixture_transport
        return ILOStatProvider(transport=ilo_fixture_transport(fixture_dir))
    return ILOStatProvider()


def get_un_wpp() -> UNWPPProvider:
    # LIFESPAN_WPP_FIXTURE_FILE points tests at a recorded (trimmed) copy of the official CSV.
    from app.core.config import DATA_DIR
    return UNWPPProvider(cache_dir=DATA_DIR / "cache", fixture_file=os.environ.get("LIFESPAN_WPP_FIXTURE_FILE") or None)


def get_un_wpp_lifetable() -> UNWPPLifeTableProvider:
    # LIFESPAN_WPP_LT_FIXTURE_DIR points tests at recorded (country-trimmed) copies of the official abridged life tables.
    from app.core.config import DATA_DIR
    return UNWPPLifeTableProvider(cache_dir=DATA_DIR / "cache", fixture_dir=os.environ.get("LIFESPAN_WPP_LT_FIXTURE_DIR") or None)


manual_provider = ManualProvider()
uae_provider = UAEStatProvider()
india_provider = IndiaMoSPIProvider()
IMPORT_PROVIDERS = {p.provider_id: p for p in (manual_provider, uae_provider, india_provider)}
