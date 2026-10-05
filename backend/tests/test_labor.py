"""Phase 4 labour evidence — offline. Real server process + recorded ILOSTAT SDMX-CSV and World Bank
responses (tests/fixtures/ilo, tests/fixtures/wb). Set LIFESPAN_LIVE_TESTS=1 for live smoke tests."""
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.providers.fixtures import ilo_fixture_transport
from app.providers.ilostat import ILOStatProvider
from app.providers.base import ProviderError
from app.providers.sdmx import parse_csv
from app.services import economic_engine as eng
from tests.conftest import Server

FIX = Path(__file__).parent / "fixtures"
EP = "ep-demo-delhi-dubai"


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFESPAN_WB_FIXTURE_DIR", str(FIX / "wb"))
    monkeypatch.setenv("LIFESPAN_ILO_FIXTURE_DIR", str(FIX / "ilo"))
    s = Server(tmp_path)
    s.start()
    yield s
    s.stop()


def ilo():
    return ILOStatProvider(transport=ilo_fixture_transport(str(FIX / "ilo")))


# ---------------- provider parsing ----------------
def test_ilostat_parsing_dimensions_and_currency():
    res = ilo().fetch_series("DF_EAR_EMTA_SEX_OCU_NB", ["ARE"], 2009, 2009)
    tot = next(o for o in res.observations if o.raw["dims"]["SEX"]["code"] == "SEX_T" and o.raw["dims"]["OCU"]["code"] == "OCU_SKILL_TOTAL")
    assert tot.value == Decimal("7450.587") and tot.raw["currency"] == "AED" and tot.unit == "AED per month"
    assert "Labour Force Survey" in tot.source_note and tot.obs_key.endswith(":SEX_T.OCU_SKILL_TOTAL:2009")


def test_median_vs_mean_and_hourly_registry():
    med = ilo().fetch_series("DF_EAR_EMTM_SEX_NB", ["IND"], 2018, 2018).observations
    assert {o.raw["statistic"] for o in med} == {"MEDIAN"} and any(o.value == Decimal("10000") for o in med)
    hr = ilo().fetch_series("DF_EAR_EHRA_SEX_NB", ["IND", "ARE"], 1990, 2024).observations
    assert all(o.raw["payPeriod"] == "HOURLY" for o in hr)


def test_missing_years_reported_not_invented():
    res = ilo().fetch_series("DF_EAR_EMTM_SEX_NB", ["IND"], 1990, 2005)
    years = {o.year for o in res.observations}
    assert years == {2005}
    assert {"country": "IND", "year": 1995, "reason": "no observation published"} in res.missing


def test_missing_dimensions_and_malformed():
    recs = parse_csv("STRUCTURE,STRUCTURE_ID,REF_AREA,Reference area,FREQ,Frequency,MEASURE,Measure,TIME_PERIOD,Time period,OBS_VALUE,Observation value\n"
                     "DATAFLOW,ILO:X(1.0),IND,India,A,Annual,M,Meas,2010,,,\n")
    assert recs[0].value is None and recs[0].dims == {}
    with pytest.raises(ProviderError):
        parse_csv("a,b\n1,2\n")
    with pytest.raises(ProviderError):
        parse_csv("REF_AREA,TIME_PERIOD,OBS_VALUE\nIND,2010,abc\n")


def test_provider_failures():
    def h429(req):
        return httpx.Response(429)
    with pytest.raises(ProviderError) as e:
        ILOStatProvider(transport=httpx.MockTransport(h429)).fetch_series("DF_EAR_EMTM_SEX_NB", ["IND"], 2010, 2010)
    assert e.value.kind == "rate-limit"

    def html(req):
        return httpx.Response(200, text="<html>Attention Required</html>")
    with pytest.raises(ProviderError) as e:
        ILOStatProvider(transport=httpx.MockTransport(html)).fetch_series("DF_EAR_EMTM_SEX_NB", ["IND"], 2010, 2010)
    assert e.value.kind == "malformed"

    def boom(req):
        raise httpx.ConnectError("down", request=req)
    with pytest.raises(ProviderError) as e:
        ILOStatProvider(transport=httpx.MockTransport(boom)).fetch_series("DF_EAR_EMTM_SEX_NB", ["IND"], 2010, 2010)
    assert e.value.kind == "network"


def test_annualize_requires_explicit_assumptions():
    r = eng.annualize_wage("10000", "MONTHLY", {})
    assert r.status == "MISSING_DATA"
    assert eng.annualize_wage("10000", "MONTHLY", {"monthsPerYear": 12}).result == "120000"
    assert eng.annualize_wage("50", "HOURLY", {"hoursPerWeek": 40}).status == "MISSING_DATA"


# ---------------- end-to-end on the server ----------------
def _ilo_sync(c, flows, countries=("IND", "ARE"), y0=1990, y1=2024):
    r = c.post("/data/ilostat/sync", json={"indicators": list(flows), "countries": list(countries), "yearStart": y0, "yearEnd": y1})
    assert r.status_code == 200, r.text
    return r.json()


def _profile(c, **kw):
    body = {"lifeStage": "first-employment", "targetYear": 2010, "yearStart": 2010, "yearEnd": 2012, "country": "IND", "region": "Delhi", "urbanRural": "URBAN",
            "educationLevel": "INT", "occupation": "Technician", "occupationCode": "3", "employmentStatus": "EMPLOYEE", "sex": "MALE", **kw}
    r = c.post(f"/episodes/{EP}/economic-profiles", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_sync_normalises_and_dedupes(srv):
    c = srv.client()
    s = _ilo_sync(c, ["DF_EAR_EMTA_SEX_OCU_NB", "DF_UNE_DEAP_SEX_AGE_RT"])
    ear = s["indicators"][0]
    assert ear["retrieved"] > 100 and ear["wageObservations"] == ear["retrieved"] and ear["unavailable"] > 0
    assert s["indicators"][1]["wageObservations"] == 0  # context indicator: not a wage
    again = _ilo_sync(c, ["DF_EAR_EMTA_SEX_OCU_NB"])
    assert again["indicators"][0]["created"] == 0 and again["indicators"][0]["unchanged"] == ear["retrieved"]
    ws = c.get("/labor/wage-observations", params={"country": "IND", "occupation": "3", "yearStart": 2010, "yearEnd": 2010}).json()
    assert ws and all(w["occupationClassification"] in ("ISCO-08", "ISCO-88", "ILO skill level") for w in ws)
    assert all(w["grossOrNet"] == "UNKNOWN" and w["employmentStatus"] == "EMPLOYEE" for w in ws)
    assert all(w["citizenship"] is None and w["region"] is None for w in ws)  # not provided -> NULL, never invented


def test_matching_ranking_year_occupation_education_country(srv):
    c = srv.client()
    _ilo_sync(c, ["DF_EAR_EMTA_SEX_OCU_NB", "DF_EAR_EMTA_SEX_EDU_NB", "DF_EAR_EMTM_SEX_NB"])
    p = _profile(c)
    res = c.get(f"/economic-profiles/{p['id']}/candidates", params={"limit": 200}).json()
    cands = res["candidates"]
    top = cands[0]
    assert top["wage"]["country"] == "IND" and top["sourceYear"] == 2010
    # India 2010 occupations are coded ISCO-88: same major group is NOT treated as an exact ISCO-08 match
    occ88 = next(x for x in cands if x["wage"]["occupationCode"] == "3" and x["wage"]["occupationClassification"] == "ISCO-88" and x["sourceYear"] == 2010)
    assert any("not assumed equivalent" in b["note"] for b in occ88["breakdown"])
    p88 = _profile(c, occupationClassification="ISCO-88")
    top88 = c.get(f"/economic-profiles/{p88['id']}/candidates").json()["candidates"][0]
    assert top88["wage"]["occupationCode"] == "3" and top88["wage"]["occupationClassification"] == "ISCO-88" and top88["sourceYear"] == 2010
    assert any(b["dimension"] == "Urban/rural" and "unavailable" in b["note"] for b in top["breakdown"])
    scores = [x["score"] for x in cands]
    assert scores == sorted(scores, reverse=True)
    # year distance is penalised
    all88 = c.get(f"/economic-profiles/{p88['id']}/candidates", params={"limit": 200}).json()["candidates"]
    by_year = {x["sourceYear"]: x["score"] for x in all88 if x["wage"]["occupationCode"] == "3" and x["wage"]["occupationClassification"] == "ISCO-88" and x["wage"]["sex"] == "MALE"}
    print(by_year); assert len(by_year) >= 2 and by_year[2010] == max(by_year.values()) and min(by_year.values()) < by_year[2010]
    # education match ranks above all-education for EDU series
    edu = {x["wage"]["educationCode"]: x["score"] for x in cands if x["wage"]["educationCode"] and x["sourceYear"] == 2010 and x["wage"]["sex"] == "MALE"}
    if "INT" in edu and "TOTAL" in edu:
        assert edu["INT"] > edu["TOTAL"]
    # country mismatch scores far lower
    uae = [x for x in cands if x["wage"]["country"] == "ARE"]
    assert all(not x["countryMatch"] for x in uae)
    assert "not a probability" in top["label"]


def test_baseline_fact_supported_derived_assumption_and_rules(srv):
    c = srv.client()
    _ilo_sync(c, ["DF_EAR_EMTA_SEX_OCU_NB"])
    c.post("/data/world-bank/sync", json={"indicators": ["FP.CPI.TOTL"], "countries": ["IN"], "yearStart": 1995, "yearEnd": 2010})
    p = _profile(c)
    top = c.get(f"/economic-profiles/{p['id']}/candidates").json()["candidates"][0]
    wid = top["wage"]["id"]
    b = c.post(f"/episodes/{EP}/baselines", json={"profileId": p["id"], "lifeStage": "first-employment", "yearStart": 2010, "yearEnd": 2012,
                                                  "baselineType": "FACT_SUPPORTED", "wageObservationIds": [wid]})
    assert b.status_code == 201, b.text
    b = b.json()
    assert b["point"] == top["wage"]["value"] and b["grossOrNet"] == "UNKNOWN" and b["confidence"] in ("HIGH", "MEDIUM")
    assert b["prototypeIncome"]["isPrototype"] and b["evidence"][0]["factId"]
    lin = c.get(f"/facts/{b['evidence'][0]['factId']}/lineage").json()
    assert lin["observation"]["provider"] == "ilostat" and lin["source"]["organization"] == "International Labour Organization"
    assert "Employees" in lin["fact"]["metric"] or "employees" in lin["fact"]["metric"].lower()

    # FACT_SUPPORTED from another year is refused; DERIVED via CPI creates lineage
    p95 = _profile(c, targetYear=1995, yearStart=1995, yearEnd=1997)
    bad = c.post(f"/episodes/{EP}/baselines", json={"profileId": p95["id"], "lifeStage": "first-employment", "yearStart": 1995, "yearEnd": 1997,
                                                    "baselineType": "FACT_SUPPORTED", "wageObservationIds": [wid]})
    assert bad.status_code == 422
    d = c.post(f"/episodes/{EP}/baselines", json={"profileId": p95["id"], "lifeStage": "first-employment", "yearStart": 1995, "yearEnd": 1997,
                                                  "baselineType": "DERIVED", "wageObservationIds": [wid], "adjustToYear": 1995})
    assert d.status_code == 201, d.text
    d = d.json()
    assert d["derivedCalculationIds"] and d["confidence"] in ("LOW", "INSUFFICIENT_DATA")
    dl = c.get(f"/facts/{d['evidence'][0]['derivedFactId']}/lineage").json()
    assert dl["calculation"]["reproducible"] and {i["role"] for i in dl["calculation"]["inputs"]} == {"source_cpi", "target_cpi"}

    # ASSUMPTION needs reasoning, creates an ASSUMPTION fact
    assert c.post(f"/episodes/{EP}/baselines", json={"lifeStage": "migration-wage", "yearStart": 2004, "yearEnd": 2006, "baselineType": "ASSUMPTION",
                                                     "low": "3000", "high": "5000", "currency": "AED", "payPeriod": "MONTHLY", "reasoning": "short"}).status_code == 422
    a = c.post(f"/episodes/{EP}/baselines", json={"lifeStage": "migration-wage", "yearStart": 2004, "yearEnd": 2006, "baselineType": "ASSUMPTION",
                                                  "low": "3000", "high": "5000", "currency": "AED", "payPeriod": "MONTHLY",
                                                  "reasoning": "No 2004 UAE wage data stored; range is an explicit research assumption pending sources."}).json()
    assert a["estimateKind"] == "RANGE" and a["assumptionFactId"]
    # NET is refused when the evidence is not net
    net = c.post(f"/episodes/{EP}/baselines", json={"profileId": p["id"], "lifeStage": "first-employment", "yearStart": 2010, "yearEnd": 2012,
                                                    "baselineType": "FACT_SUPPORTED", "wageObservationIds": [wid], "grossOrNet": "NET"})
    assert net.status_code == 422
    # prototype facts cannot support a verified baseline
    pr = c.post(f"/episodes/{EP}/baselines", json={"lifeStage": "migration-wage", "yearStart": 2004, "yearEnd": 2004, "baselineType": "FACT_SUPPORTED",
                                                   "wageObservationIds": [wid], "evidenceFactIds": ["F-008"]})
    assert pr.status_code == 422 and "PROTOTYPE" in pr.text
    # annualization must have explicit assumptions
    an = c.post(f"/episodes/{EP}/baselines", json={"profileId": p["id"], "lifeStage": "first-employment", "yearStart": 2010, "yearEnd": 2012,
                                                   "baselineType": "FACT_SUPPORTED", "wageObservationIds": [wid], "annualization": {"assumptions": {}}})
    assert an.status_code == 422
    # approval + audits
    c.post(f"/baselines/{b['id']}/approve")
    audits = c.get(f"/episodes/{EP}/audits").json()
    titles = {x["title"]: x for x in audits}
    assert "Approved baseline not yet pinned" in titles
    assert titles["Wage evidence year differs substantially from target"]["outcome"] == "WARNING"


def test_csv_import_preview_duplicates_changed_and_distribution(srv):
    c = srv.client()
    csv1 = ("metric,value,unit,currency,country,year,source,source_organization,pay_period,statistic_type,citizenship,sex,bin_lower,bin_upper,count\n"
            "Median monthly earnings regular wage employees,12000,INR per month,INR,IND,2019,PLFS 2018-19 Table 42,MoSPI,MONTHLY,MEDIAN,,,,,\n"
            "Median monthly earnings regular wage employees,12000,INR per month,INR,IND,2019,PLFS 2018-19 Table 42,MoSPI,MONTHLY,MEDIAN,,,,,\n"
            "Employed by monthly wage group,,AED per month,AED,ARE,2019,Labour Force Survey,FCSC,MONTHLY,DISTRIBUTION,NON_NATIONAL,MALE,5000,9999,120000\n"
            "Employed by monthly wage group,,AED per month,AED,ARE,2019,Labour Force Survey,FCSC,MONTHLY,DISTRIBUTION,NON_NATIONAL,MALE,,999,80000\n"
            "Bad row,abc,INR,INR,India,19,x,y,MONTHLY,MEDIAN,,,,,\n")
    pv = c.post("/labor/import/preview", json={"provider": "india-mospi", "csv": csv1}).json()
    assert (pv["rowsDetected"], pv["valid"], pv["invalid"], pv["duplicates"]) == (5, 3, 1, 1)
    assert c.get("/labor/wage-observations", params={"provider": "india-mospi"}).json() == []  # preview saves nothing
    cm = c.post("/labor/import/commit", json={"provider": "india-mospi", "csv": csv1}).json()
    assert cm["imported"] == 3
    again = c.post("/labor/import/preview", json={"provider": "india-mospi", "csv": csv1}).json()
    assert again["duplicates"] == 4 and again["valid"] == 0
    changed = csv1.replace(",12000,", ",12500,")
    assert c.post("/labor/import/preview", json={"provider": "india-mospi", "csv": changed}).json()["changed"] == 1
    c.post("/labor/import/commit", json={"provider": "india-mospi", "csv": changed})
    obs = [o for o in c.get("/data/observations", params={"provider": "india-mospi"}).json() if o["value"] == "12500"]
    assert obs and obs[0]["revisions"] == 1  # old value preserved as a revision
    d = c.get("/labor/distributions", params={"country": "ARE"}).json()
    assert len(d) == 1 and len(d[0]["bins"]) == 2
    open_bin = next(x for x in d[0]["bins"] if x["openLower"])
    assert open_bin["upperBound"] == "999" and d[0]["dimensions"]["citizenship"] == "NON_NATIONAL"
    assert c.post("/labor/import/preview", json={"provider": "manual", "csv": "value\n1\n"}).json()["errors"]


def test_snapshot_create_immutable_versions_diff_restart(srv, tmp_path):
    c = srv.client()
    _ilo_sync(c, ["DF_EAR_EMTA_SEX_OCU_NB"])
    p = _profile(c)
    wid = c.get(f"/economic-profiles/{p['id']}/candidates").json()["candidates"][0]["wage"]["id"]
    b = c.post(f"/episodes/{EP}/baselines", json={"profileId": p["id"], "lifeStage": "first-employment", "yearStart": 2010, "yearEnd": 2012,
                                                  "baselineType": "FACT_SUPPORTED", "wageObservationIds": [wid]}).json()
    c.post(f"/baselines/{b['id']}/approve")
    s1 = c.post(f"/episodes/{EP}/snapshots", json={"name": "Delhi-Dubai Baseline"}).json()
    assert s1["name"] == "Delhi-Dubai Baseline v1" and s1["status"] == "draft"
    assert s1["counts"]["baselines"] == 1 and s1["counts"]["observations"] >= 1 and s1["counts"]["verifiedFacts"] >= 1
    f1 = c.post(f"/snapshots/{s1['id']}/finalize").json()
    assert f1["status"] == "final" and f1["intact"] is True and len(f1["contentHash"]) == 64
    assert c.post(f"/snapshots/{s1['id']}/refresh").status_code == 409
    assert c.delete(f"/snapshots/{s1['id']}").status_code == 409
    assert c.post(f"/snapshots/{s1['id']}/finalize").status_code == 409

    # database itself refuses tampering
    db = sqlite3.connect(str(tmp_path / "lifespan.db"))
    with pytest.raises(sqlite3.DatabaseError):
        db.execute("UPDATE snapshot_observations SET value='1' WHERE snapshot_id=?", (s1["id"],))
        db.commit()
    db.rollback()

    # change evidence: new baseline, new version
    c.post(f"/episodes/{EP}/baselines", json={"lifeStage": "migration-wage", "yearStart": 2004, "yearEnd": 2006, "baselineType": "ASSUMPTION", "point": "4000",
                                              "currency": "AED", "payPeriod": "MONTHLY", "reasoning": "Explicit placeholder assumption pending UAE sources."})
    s2 = c.post(f"/snapshots/{s1['id']}/new-version").json()
    assert s2["name"] == "Delhi-Dubai Baseline v2" and s2["parentId"] == s1["id"] and s2["counts"]["baselines"] == 2
    diff = c.get("/snapshots/diff", params={"a": s1["id"], "b": s2["id"]}).json()
    kinds = {x["kind"] for x in diff["baselines"]}
    assert "added" in kinds and "unchanged" in kinds
    srv.restart()
    c = srv.client()
    again = c.get(f"/snapshots/{s1['id']}").json()
    assert again["status"] == "final" and again["intact"] is True and len(again["baselines"]) == 1
    audits = {a["title"] for a in c.get(f"/episodes/{EP}/audits").json()}
    assert "Finalized dataset snapshot modified" not in audits

    # tamper bypassing triggers -> audit FAIL
    db = sqlite3.connect(str(tmp_path / "lifespan.db"))
    db.execute("DROP TRIGGER snapshot_observations_final_update")
    db.execute("UPDATE snapshot_observations SET value='1' WHERE snapshot_id=?", (s1["id"],))
    db.commit()
    audits = {a["title"]: a["outcome"] for a in c.get(f"/episodes/{EP}/audits").json()}
    assert audits["Finalized dataset snapshot modified"] == "FAIL"


def test_gaps_tasks_readiness_households(srv):
    c = srv.client()
    _ilo_sync(c, ["DF_EAR_EMTA_SEX_OCU_NB"])
    _profile(c, targetYear=1990, yearStart=1990, yearEnd=1993)
    _profile(c, lifeStage="migration-wage", targetYear=2004, yearStart=2004, yearEnd=2010, country="ARE", region="Dubai", citizenship="NON_NATIONAL")
    gaps = c.post(f"/episodes/{EP}/evidence-gaps/detect").json()
    keys = {g["title"] for g in gaps}
    assert any("1990–1993" in t for t in keys) and any("2004–2010" in t for t in keys)
    assert any("housing" in t for t in keys)
    g = next(x for x in gaps if "1990–1993" in x["title"])
    assert g["priority"] == "HIGH"
    t = c.post(f"/evidence-gaps/{g['id']}/research-task").json()
    tasks = c.get("/snapshot").json()["tasks"]
    assert any(x["id"] == t["taskId"] and x["status"] == "pending" for x in tasks)
    r = c.get(f"/episodes/{EP}/readiness").json()
    st = {s["stage"]: s["status"] for s in r["stages"]}
    assert st["housing"] == "MISSING" and 0 <= r["overall"] < 100
    h = c.post(f"/episodes/{EP}/households", json={"label": "Dubai household", "yearStart": 2004, "yearEnd": 2018,
                                                   "members": [{"role": "self"}, {"role": "spouse"}]}).json()
    assert h["members"][1]["employmentKind"] == "unknown"
    assert c.post(f"/households/{h['id']}/streams", json={"kind": "remittance-sent", "yearStart": 2004, "yearEnd": 2018, "low": "500", "currency": "AED"}).status_code == 422
    ok = c.post(f"/households/{h['id']}/streams", json={"kind": "remittance-sent", "yearStart": 2004, "yearEnd": 2018})
    assert ok.status_code == 201  # structure without an invented amount


@pytest.mark.skipif(os.environ.get("LIFESPAN_LIVE_TESTS") != "1", reason="live ILOSTAT test (set LIFESPAN_LIVE_TESTS=1)")
def test_live_ilostat():
    res = ILOStatProvider().fetch_series("DF_EAR_EMTM_SEX_NB", ["IND"], 2018, 2018)
    assert any(o.raw["dims"]["SEX"]["code"] == "SEX_T" and o.value > 0 for o in res.observations)


@pytest.mark.skipif(os.environ.get("LIFESPAN_LIVE_TESTS") != "1", reason="live UAE test (set LIFESPAN_LIVE_TESTS=1)")
def test_live_uae_fcsc_reachability():
    from app.providers.official_import import UAEStatProvider
    ok, kind = UAEStatProvider().ping()
    assert ok, f"UAE .Stat not reachable: {kind}"
