"""Provider registry. Tests replace providers with recorded-response transports via env vars."""
from __future__ import annotations

import os

from app.providers.ilostat import ILOStatProvider
from app.providers.manual import ManualProvider
from app.providers.official_import import IndiaMoSPIProvider, UAEStatProvider
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


manual_provider = ManualProvider()
uae_provider = UAEStatProvider()
india_provider = IndiaMoSPIProvider()
IMPORT_PROVIDERS = {p.provider_id: p for p in (manual_provider, uae_provider, india_provider)}
