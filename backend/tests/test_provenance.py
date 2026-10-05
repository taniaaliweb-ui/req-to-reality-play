"""End-to-end truth pipeline on the REAL server process, using recorded World Bank responses
(LIFESPAN_WB_FIXTURE_DIR) so no internet is needed:
observation → Fact → derived calculation → derived Fact, traced backwards, surviving a restart."""
from decimal import Decimal
from pathlib import Path

import pytest

from tests.conftest import Server

FIX = str(Path(__file__).parent / "fixtures" / "wb")
EP = "ep-demo-delhi-dubai"


@pytest.fixture()
def wb_server(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFESPAN_WB_FIXTURE_DIR", FIX)
    srv = Server(tmp_path)
    srv.start()
    yield srv
    srv.stop()


def _sync(c, indicators, countries, y0, y1):
    r = c.post("/data/world-bank/sync", json={"indicators": indicators, "countries": countries, "yearStart": y0, "yearEnd": y1})
    assert r.status_code == 200, r.text
    return r.json()


def test_full_lineage_survives_restart(wb_server):
    c = wb_server.client()
    s = _sync(c, ["FP.CPI.TOTL", "PA.NUS.FCRF"], ["IN", "AE"], 1995, 2010)
    assert s["retrieved"] > 0 and s["unavailable"] > 0  # UAE CPI before 2007 genuinely missing
    assert s["status"] == "partial"

    r = c.post("/economics/inflation-adjust", json={"episodeId": EP, "country": "IND", "amount": "100000", "sourceYear": 1995, "targetYear": 2010, "save": True}).json()
    assert r["status"] == "OK" and r["display"] == "264934.05"
    der = r["factId"]

    fx = c.post("/economics/currency-convert", json={"episodeId": EP, "amount": "500000", "year": 1998, "fromCountry": "IND", "toCountry": "ARE", "save": True}).json()
    assert fx["status"] == "OK" and "annual-average" in fx["labels"][0]

    wb_server.restart()
    c = wb_server.client()
    lin = c.get(f"/facts/{der}/lineage").json()
    assert lin["fact"]["factType"] == "DERIVED"
    calc = lin["calculation"]
    assert calc["formulaVersion"] == "inflation-adjust-v1" and calc["reproducible"] is True
    roles = {i["role"]: i for i in calc["inputs"]}
    assert roles["source_cpi"]["observation"]["id"] == "world-bank:FP.CPI.TOTL:IND:1995"
    assert roles["source_cpi"]["source"]["id"] == "SRC-WB-WDI"
    assert Decimal(roles["source_cpi"]["fact"]["value"]) == Decimal("37.7452131691141")

    fxl = c.get(f"/facts/{fx['factId']}/lineage").json()
    fr = {i["role"]: i for i in fxl["calculation"]["inputs"]}
    assert fr["source_fx"]["observation"]["indicatorCode"] == "PA.NUS.FCRF"
    assert fr["target_fx"]["observation"]["countryCode"] == "ARE"

    audits = c.get(f"/episodes/{EP}/audits").json()
    assert any(a["outcome"] == "PASS" and "complete lineage" in a["title"] for a in audits)


def test_missing_cpi_returns_missing_data(wb_server):
    c = wb_server.client()
    _sync(c, ["FP.CPI.TOTL"], ["AE"], 1995, 2010)
    r = c.post("/economics/inflation-adjust", json={"episodeId": EP, "country": "ARE", "amount": "1000", "sourceYear": 1998, "targetYear": 2010, "save": True}).json()
    assert r["status"] == "MISSING_DATA" and r["missing"] == ["CPI ARE 1998"] and "factId" not in r


def test_derived_without_lineage_fails_audit(wb_server):
    c = wb_server.client()
    f = {"episodeId": EP, "category": "Economy", "metric": "hand-typed derived", "value": "5", "unit": "INR", "country": "India", "region": "",
         "yearStart": 2000, "yearEnd": 2000, "sourceId": None, "confidence": "low", "factType": "DERIVED", "notes": "", "status": "verified"}
    assert c.put(f"/episodes/{EP}/facts/F-X1", json=f).status_code == 200
    audits = c.get(f"/episodes/{EP}/audits").json()
    fail = [a for a in audits if a["title"] == "Verified DERIVED value without calculation lineage"]
    assert fail and fail[0]["outcome"] == "FAIL" and "F-X1" in fail[0]["refs"]


def test_input_fact_protected_and_refresh_audited(wb_server):
    c = wb_server.client()
    _sync(c, ["FP.CPI.TOTL"], ["IN"], 2000, 2001)
    r = c.post("/economics/inflation-adjust", json={"episodeId": EP, "country": "IND", "amount": "10", "sourceYear": 2000, "targetYear": 2001, "save": True}).json()
    lin = c.get(f"/facts/{r['factId']}/lineage").json()
    inp = lin["calculation"]["inputs"][0]["fact"]["id"]
    assert c.delete(f"/episodes/{EP}/facts/{inp}").status_code == 409
    # Re-sync identical data: nothing duplicated, nothing revised
    s = _sync(c, ["FP.CPI.TOTL"], ["IN"], 2000, 2001)
    assert s["indicators"][0]["created"] == 0 and s["indicators"][0]["unchanged"] == 2


def test_disabled_in_settings(wb_server):
    c = wb_server.client()
    st = c.get("/settings").json()
    c.put("/settings", json={**st, "worldBankEnabled": False})
    r = c.post("/data/world-bank/sync", json={"indicators": ["FP.CPI.TOTL"], "countries": ["IN"], "yearStart": 2000, "yearEnd": 2001})
    assert r.status_code == 403
    assert c.get("/data/providers").json()[0]["status"] == "disabled"


def test_prototype_marked_verified_fails(wb_server):
    audits = wb_server.client().get(f"/episodes/{EP}/audits").json()
    assert any(a["outcome"] == "FAIL" and "PROTOTYPE" in a["title"] for a in audits)
