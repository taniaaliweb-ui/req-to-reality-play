"""Provider registry. Tests replace `get_world_bank` to inject a mocked transport."""
from __future__ import annotations

import os

import httpx

from app.providers.manual import ManualProvider
from app.providers.world_bank import WorldBankProvider


def get_world_bank() -> WorldBankProvider:
    # LIFESPAN_WB_FIXTURE_DIR lets automated tests run the real server against recorded responses.
    fixture_dir = os.environ.get("LIFESPAN_WB_FIXTURE_DIR")
    if fixture_dir:
        from app.providers.fixtures import fixture_transport
        return WorldBankProvider(transport=fixture_transport(fixture_dir))
    return WorldBankProvider()


manual_provider = ManualProvider()
