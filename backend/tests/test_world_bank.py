"""World Bank adapter against mocked HTTP — the suite never needs the internet.
Set LIFESPAN_LIVE_TESTS=1 to also run a live smoke test."""
import json
import os
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.fixtures import fixture_transport
from app.providers.world_bank import WorldBankProvider

FIX = Path(__file__).parent / "fixtures" / "wb"


def provider(handler) -> WorldBankProvider:
    return WorldBankProvider(transport=httpx.MockTransport(handler))


def test_success_recorded_india_cpi():
    p = WorldBankProvider(transport=fixture_transport(str(FIX)))
    res = p.fetch_series("FP.CPI.TOTL", ["IN"], 1995, 2010)
    by_year = {o.year: o for o in res.observations}
    assert by_year[2010].value == Decimal(100)
    assert by_year[1995].value == Decimal("37.7452131691141")  # full precision kept
    assert by_year[1995].country_code == "IND" and by_year[1995].provider_last_updated == "2026-07-13"
    assert res.missing == []


def test_missing_years_reported_not_invented():
    p = WorldBankProvider(transport=fixture_transport(str(FIX)))
    res = p.fetch_series("FP.CPI.TOTL", ["AE"], 1995, 2010)
    years = {o.year for o in res.observations}
    assert 1995 not in years and 2010 in years
    assert {"country": "AE", "year": 1995, "reason": "no value published"} in res.missing


def _wb(rows, header=None):
    return [header or {"page": 1, "pages": 1, "lastupdated": "2026-01-01"}, rows]


def _row(year, value):
    return {"indicator": {"id": "FP.CPI.TOTL", "value": "CPI"}, "country": {"id": "IN", "value": "India"}, "countryiso3code": "IND", "date": str(year), "value": value}


def test_null_value_and_year_outside_response():
    def h(req):
        if "/country/" in req.url.path:
            return httpx.Response(200, json=_wb([_row(2001, 10.5), _row(2000, None)]))
        return httpx.Response(200, json=_wb([{"name": "CPI", "sourceNote": "n", "sourceOrganization": "IMF"}]))
    res = provider(h).fetch_series("FP.CPI.TOTL", ["IN"], 2000, 2002)
    assert [o.year for o in res.observations] == [2001]
    assert [(x["year"], x["reason"]) for x in res.missing] == [(2000, "no value published"), (2002, "not in provider response")]
    assert res.observations[0].source_organization == "IMF"


def test_invalid_country():
    def h(req):
        if "/country/" in req.url.path:
            return httpx.Response(200, json=[{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}])
        return httpx.Response(200, json=_wb([{"name": "CPI"}]))
    res = provider(h).fetch_series("FP.CPI.TOTL", ["ZZ"], 2000, 2001)
    assert res.countries_unknown == ["ZZ"] and res.observations == []
    with pytest.raises(ProviderError) as e:
        provider(h).fetch_series("FP.CPI.TOTL", ["1!"], 2000, 2001)
    assert e.value.kind == "invalid-request"


def test_provider_http_error():
    with pytest.raises(ProviderError) as e:
        provider(lambda req: httpx.Response(503, text="down")).fetch_series("FP.CPI.TOTL", ["IN"], 2000, 2001)
    assert e.value.kind == "http"


def test_timeout():
    def h(req):
        raise httpx.ReadTimeout("slow", request=req)
    with pytest.raises(ProviderError) as e:
        provider(h).fetch_series("FP.CPI.TOTL", ["IN"], 2000, 2001)
    assert e.value.kind == "timeout"


def test_malformed_response():
    def h(req):
        if "/country/" in req.url.path:
            return httpx.Response(200, text="<html>not json</html>")
        return httpx.Response(200, json=_wb([{"name": "CPI"}]))
    with pytest.raises(ProviderError) as e:
        provider(h).fetch_series("FP.CPI.TOTL", ["IN"], 2000, 2001)
    assert e.value.kind == "malformed"

    def h2(req):
        if "/country/" in req.url.path:
            return httpx.Response(200, json=_wb([{"date": "2000", "value": "x1", "indicator": {"id": "FP.CPI.TOTL"}, "country": {"id": "IN"}}]))
        return httpx.Response(200, json=_wb([{"name": "CPI"}]))
    with pytest.raises(ProviderError):
        provider(h2).fetch_series("FP.CPI.TOTL", ["IN"], 2000, 2000)


@pytest.mark.skipif(os.environ.get("LIFESPAN_LIVE_TESTS") != "1", reason="live network test (set LIFESPAN_LIVE_TESTS=1)")
def test_live_smoke():
    res = WorldBankProvider().fetch_series("PA.NUS.FCRF", ["IN"], 2010, 2010)
    assert res.observations and res.observations[0].value > 0
    json.dumps(res.observations[0].raw)
