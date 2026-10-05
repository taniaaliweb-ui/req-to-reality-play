"""Phase 5 life-context evidence — offline. Real server + recorded UN WPP CSV (tests/fixtures/wpp,
trimmed copy of the official WPP2024 Demographic Indicators file for India + UAE), recorded ILOSTAT
and World Bank responses. Set LIFESPAN_LIVE_TESTS=1 for live smoke tests."""
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.providers.un_wpp import UNWPPProvider
from app.services.life_context import coverage_for_years
from tests.conftest import Server

FIX = Path(__file__).parent / "fixtures"
WPP = FIX / "wpp" / "WPP2024_Demographic_Indicators_Medium.csv.gz"
EP = "ep-demo-delhi-dubai"


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFESPAN_WB_FIXTURE_DIR", str(FIX / "wb"))
    monkeypatch.setenv("LIFESPAN_ILO_FIXTURE_DIR", str(FIX / "ilo"))
    monkeypatch.setenv("LIFESPAN_WPP_FIXTURE_FILE", str(WPP))
    s = Server(tmp_path)
    s.start()
    yield s
    s.stop()


def _wpp(c, y0=1965, y1=2065):
    r = c.post("/data/un-wpp/sync", json={"countries": ["IND", "ARE"], "yearStart": y0, "yearEnd": y1})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- provider / normalisation ----------------
def test_wpp_parsing_exact_values_and_projection_label(tmp_path):
    p = UNWPPProvider(cache_dir=tmp_path, fixture_file=str(WPP))
    res = p.fetch_many(["LExMale", "TFR", "IMR", "NetMigrations"], ["IND"], 1970, 2030)
    by = {(o.indicator_code, o.year): o for o in res.observations}
    assert by[("TFR", 1970)].value == Decimal("5.624")
    assert by[("LExMale", 1970)].value == Decimal("49.1228")
    assert by[("IMR", 2009)].value == Decimal("47.8167")
    assert by[("NetMigrations", 2009)].unit == "thousand persons"
    assert by[("TFR", 2030)].raw["projection"] is True and "PROJECTION" in by[("TFR", 2030)].source_note
    assert by[("TFR", 2009)].raw["projection"] is False
    assert res.countries_unknown == []
    assert p.fetch_many(["TFR"], ["XXX"], 1970, 1971).countries_unknown == ["XXX"]


def test_wpp_sync_normalises_domains(srv):
    c = srv.client()
    s = _wpp(c)
    assert s["retrieved"] > 4000 and s["projections"] > 0 and s["lifeObservations"] == s["retrieved"]
    again = _wpp(c)
    assert again["created"] == 0 and again["unchanged"] == s["retrieved"]
    mort = c.get("/life/observations", params={"domain": "mortality", "country": "IND", "metric": "LExMale", "yearStart": 1970, "yearEnd": 1970}).json()
    assert mort[0]["value"] == "49.1228" and mort[0]["sex"] == "MALE" and mort[0]["statisticKind"] == "POPULATION_STATISTIC"
    fert = c.get("/life/observations", params={"domain": "fertility", "country": "ARE", "metric": "TFR", "yearStart": 2009, "yearEnd": 2009}).json()
    assert fert and fert[0]["region"] is None and fert[0]["geoLevel"] == "NATIONAL"
    mig = c.get("/life/observations", params={"domain": "migration", "country": "ARE", "yearStart": 2004, "yearEnd": 2004}).json()
    assert {x["metric"] for x in mig} == {"NetMigrations", "CNMR"}
    proj = c.get("/life/observations", params={"domain": "mortality", "country": "IND", "yearStart": 2050, "yearEnd": 2050}).json()
    assert proj and all(x["observationType"] == "PROJECTION" for x in proj)


def test_structured_import_education_housing_family(srv):
    c = srv.client()
    csv_text = ("domain,metric,metric_label,value,unit,country,year,geo_level,region,sex,source,source_organization,observation_type,currency\n"
                "family_formation,smam,Singulate mean age at marriage,24.9,years,IND,1991,NATIONAL,,MALE,Census of India 1991,Office of the Registrar General,CENSUS,\n"
                "housing,rent_index,Rent index,112.5,index,IND,2005,CITY,Delhi,,Housing index table,National Housing Bank,ADMINISTRATIVE,\n"
                "education,enrollment_rate,Gross enrollment,abc,%,IND,1980,,,,X,Y,,\n"
                "education_cost,tuition,Annual tuition,1200,INR per year,IND,1990,NATIONAL,,,Survey table,MoSPI,SURVEY,INR\n")
    pre = c.post("/life/import/preview", json={"provider": "india-mospi", "csv": csv_text}).json()
    assert pre["valid"] == 3 and any("not a number" in e for r in pre["rows"] for e in r["errors"])
    com = c.post("/life/import/commit", json={"provider": "india-mospi", "csv": csv_text}).json()
    assert com["committed"] == 3
    fam = c.get("/life/observations", params={"domain": "family_formation"}).json()
    assert fam[0]["value"] == "24.9" and fam[0]["observationType"] == "CENSUS" and fam[0]["provider"] == "india-mospi"
    h = c.get("/life/observations", params={"domain": "housing"}).json()
    assert h[0]["geoLevel"] == "CITY" and h[0]["region"] == "Delhi"
    missing_hdr = c.post("/life/import/preview", json={"provider": "manual", "csv": "metric,value\nx,1\n"}).json()
    assert missing_hdr["errors"]


# ---------------- temporal coverage + matching ----------------
def test_temporal_coverage_rules():
    cov = {c["year"]: c for c in coverage_for_years(list(range(2004, 2012)), {2009: ["w"]}, 1, derived_years={2005})}
    assert cov[2009]["coverage"] == "DIRECT"
    assert cov[2008]["coverage"] == "NEARBY" and cov[2010]["coverage"] == "NEARBY"
    assert cov[2005]["coverage"] == "DERIVED"
    assert cov[2004]["coverage"] == "MISSING" and "not allowed" in cov[2004]["note"]
    assumed = coverage_for_years([2004], {}, 1, assumed_years={2004})
    assert assumed[0]["coverage"] == "ASSUMED"


def test_matrix_cells_match_scores_and_windows(srv):
    c = srv.client()
    _wpp(c)
    mx = c.get(f"/episodes/{EP}/life/matrix").json()
    st = {s["stage"]: s for s in mx["stages"]}
    assert st["birth"]["status"] == "READY"
    assert st["migration"]["applicable"] and st["migration"]["countries"] == ["ARE", "IND"]  # 2002–2004: origin then destination
    assert "ARE" in st["mid-career"]["countries"]
    housing = next(x for x in st["mid-career"]["cells"] if x["domain"] == "housing")
    assert housing["status"] == "MISSING"
    cell = c.get(f"/episodes/{EP}/life/matrix/birth/mortality").json()["cell"]
    top = cell["supporting"][0]
    assert top["match"]["label"].endswith("(not a probability)") and top["match"]["score"] <= 100
    assert cell["windowYears"] == 2 and cell["windowReason"]
    assert any("not the character's outcome" in r for r in cell["reasons"])
    death = next(x for x in st["death"]["cells"] if x["domain"] == "mortality")
    assert death["counts"]["DERIVED"] > 0  # future years rely on UN projections, labelled DERIVED


def test_event_relevance_dubai_2009(srv):
    c = srv.client()
    ev = {e["id"]: e for e in c.get(f"/episodes/{EP}/life/events").json()["events"]}
    assert any(m["relevance"] == "RELEVANT" and m["stage"] == "mid-career" for m in ev["EV-2008-GFC"]["matches"])
    assert any(m["relevance"] == "RELEVANT" for m in ev["EV-2009-DUBAI"]["matches"])
    assert ev["EV-1997-AFC"]["matches"] == []  # Asian crisis: geography does not include IND/ARE
    assert all(m["relevance"] == "POSSIBLY_RELEVANT" for m in ev["EV-2001-GUJARAT"]["matches"])  # different region
    assert ev["EV-2008-GFC"]["verification"] == "unverified"


# ---------------- wage anchor correction ----------------
def test_phase4_wage_is_anchor_not_period_evidence(srv):
    c = srv.client()
    c.post("/data/ilostat/sync", json={"indicators": ["DF_EAR_EMTA_SEX_OCU_NB"], "countries": ["ARE"], "yearStart": 2009, "yearEnd": 2009})
    p = c.post(f"/episodes/{EP}/economic-profiles", json={"lifeStage": "migration-wage", "targetYear": 2009, "yearStart": 2004, "yearEnd": 2018, "country": "ARE",
                                                          "region": "Dubai", "occupation": "Technician", "occupationCode": "3", "employmentStatus": "EMPLOYEE",
                                                          "sex": "MALE"}).json()
    top = c.get(f"/economic-profiles/{p['id']}/candidates").json()["candidates"][0]
    b = c.post(f"/episodes/{EP}/baselines", json={"profileId": p["id"], "lifeStage": "migration-wage", "yearStart": 2004, "yearEnd": 2018,
                                                  "baselineType": "FACT_SUPPORTED", "wageObservationIds": [top["wage"]["id"]]}).json()
    tc = b["temporalCoverage"]
    assert tc["semantics"] == "WAGE_ANCHOR" and tc["directCoverage"] == [2009]
    cov = {x["year"]: x["coverage"] for x in tc["years"]}
    assert cov[2009] == "DIRECT" and cov[2008] == "NEARBY" and cov[2010] == "NEARBY" and cov[2004] == "MISSING" and cov[2018] == "MISSING"
    assert len(tc["unresolvedYears"]) == 12
    audits = c.get(f"/episodes/{EP}/audits").json()
    assert any(a["title"] == "Direct wage evidence used outside its anchor year" and b["id"] in a["refs"] for a in audits)


# ---------------- baselines, assumptions, readiness, gaps ----------------
def test_life_baseline_rules_and_assumption_register(srv):
    c = srv.client()
    _wpp(c)
    lo = c.get("/life/observations", params={"domain": "mortality", "country": "IND", "metric": "IMR", "yearStart": 1970, "yearEnd": 1970}).json()[0]
    ok = c.post(f"/episodes/{EP}/life/baselines", json={"domain": "mortality", "lifeStage": "birth", "yearStart": 1970, "yearEnd": 1970,
                                                         "lifeObservationIds": [lo["id"]], "reasoning": "UN WPP infant mortality at birth year."})
    assert ok.status_code == 201, ok.text
    ok = ok.json()
    assert ok["coverageType"] == "DIRECT" and ok["point"] == lo["value"]
    ext = c.post(f"/episodes/{EP}/life/baselines", json={"domain": "mortality", "lifeStage": "childhood", "yearStart": 1970, "yearEnd": 1980,
                                                          "lifeObservationIds": [lo["id"]]})
    assert ext.status_code == 422 and "Unsupported period extension" in ext.text
    none = c.post(f"/episodes/{EP}/life/baselines", json={"domain": "housing", "lifeStage": "mid-career", "yearStart": 2005, "yearEnd": 2010})
    assert none.status_code == 422
    short = c.post(f"/episodes/{EP}/assumptions", json={"domain": "housing", "lifeStage": "mid-career", "claim": "Shared flat", "reason": "too short"})
    assert short.status_code == 422
    a = c.post(f"/episodes/{EP}/assumptions", json={"domain": "housing", "lifeStage": "mid-career", "claim": "Character rents a shared room in Dubai",
                                                    "value": "1500-2500", "unit": "AED per month", "yearStart": 2005, "yearEnd": 2010,
                                                    "reason": "No official Dubai rent statistics stored for 2005–2010; explicit research assumption."}).json()
    asb = c.post(f"/episodes/{EP}/life/baselines", json={"domain": "housing", "lifeStage": "mid-career", "yearStart": 2005, "yearEnd": 2010,
                                                          "assumptionIds": [a["id"]], "low": "1500", "high": "2500", "unit": "AED per month"}).json()
    assert asb["coverageType"] == "ASSUMED" and asb["confidence"] == "LOW" and asb["estimateKind"] == "RANGE"
    reg = c.get(f"/episodes/{EP}/assumptions").json()
    assert any(x["id"] == a["id"] and x["kind"] == "register" for x in reg)
    assert any(x["kind"] == "fact" for x in reg)  # Phase 1–4 ASSUMPTION facts are listed too
    # readiness: assumption makes cell PARTIAL, not READY
    cell = c.get(f"/episodes/{EP}/life/matrix/mid-career/housing").json()["cell"]
    assert cell["status"] == "PARTIAL" and cell["counts"]["ASSUMED"] == 6
    rd = c.get(f"/episodes/{EP}/life/readiness").json()
    assert rd["overall"] == "NOT_READY" and rd["blocking"]
    grp = {g["key"]: g for g in rd["groups"]}
    assert grp["demographic"]["status"] in ("READY", "PARTIAL") and grp["housing"]["status"] == "PARTIAL"
    assert "not statistical confidence" in rd["note"]


def test_life_gaps_to_research_tasks(srv):
    c = srv.client()
    _wpp(c)
    gaps = c.post(f"/episodes/{EP}/life/gaps/detect").json()
    life_gaps = [g for g in gaps if g["gapKey"].startswith("life:")]
    hous = next(g for g in life_gaps if g["gapKey"] == "life:mid-career:housing")
    assert hous["priority"] == "HIGH" and hous["domain"] == "housing" and hous["lifeStage"] == "mid-career" and "Dubai" in hous["title"]
    assert not any(g["gapKey"] == "life:birth:mortality" for g in life_gaps)  # covered by UN WPP
    # Phase 4 detection must not resolve life gaps
    c.post(f"/episodes/{EP}/evidence-gaps/detect")
    again = {g["gapKey"]: g for g in c.get(f"/episodes/{EP}/evidence-gaps").json()}
    assert again["life:mid-career:housing"]["status"] == "open"
    t = c.post(f"/evidence-gaps/{hous['id']}/research-task").json()
    assert t["taskId"]
    cell = c.get(f"/episodes/{EP}/life/matrix/mid-career/housing").json()["cell"]
    assert cell["gaps"] and cell["researchTasks"][0]["id"] == t["taskId"]


def test_migration_path_policy_and_context(srv):
    c = srv.client()
    _wpp(c)
    paths = c.get(f"/episodes/{EP}/life/migration-paths").json()
    p = next(x for x in paths if x["origin"] == "IND" and x["destination"] == "ARE")
    assert p["auto"] and p["observations"] and any("bilateral" in m for m in p["missing"]) and "No probability" in p["note"]
    assert any(x["id"] == "POL-IND-EMIG-1983" for x in p["policies"])
    bad = c.post("/life/context", json={"topic": "marriage-norms", "country": "IND", "yearStart": 1990, "yearEnd": 2000, "populationScope": "x",
                                         "claim": "short", "source": "s", "evidenceType": "QUALITATIVE"})
    assert bad.status_code == 422
    ctx = c.post("/life/context", json={"topic": "marriage-norms", "country": "IND", "yearStart": 1990, "yearEnd": 2000, "populationScope": "Urban Delhi households",
                                         "claim": "Arranged marriage remained the predominant form (test record).", "source": "Test source",
                                         "evidenceType": "QUALITATIVE"}).json()
    assert ctx["dataKind"] == "QUALITATIVE_CONTEXT"
    cell = c.get(f"/episodes/{EP}/life/matrix/marriage-family/marriage").json()["cell"]
    assert any(x["type"] == "context" for x in cell["extra"])
    assert c.post(f"/life/policies/POL-IND-EMIG-1983/verify").json()["verification"] == "verified"


# ---------------- snapshots ----------------
def test_snapshot_manifest_immutability_and_persistence(srv):
    c = srv.client()
    _wpp(c)
    a = c.post(f"/episodes/{EP}/assumptions", json={"domain": "housing", "lifeStage": "mid-career", "claim": "Character rents a shared room",
                                                    "yearStart": 2005, "yearEnd": 2006, "reason": "Explicit assumption pending official rent data."}).json()
    c.post(f"/episodes/{EP}/life/baselines", json={"domain": "housing", "lifeStage": "mid-career", "yearStart": 2005, "yearEnd": 2006, "assumptionIds": [a["id"]], "point": "2000"})
    c.post(f"/episodes/{EP}/life/gaps/detect")
    s = c.post(f"/episodes/{EP}/snapshots", json={"name": "Delhi–Dubai Evidence Snapshot"}).json()
    f = c.post(f"/snapshots/{s['id']}/finalize").json()
    d = c.get(f"/snapshots/{s['id']}").json()
    man = {x["label"]: x["count"] for x in d["manifest"]["lines"]}
    assert man["UN WPP observations"] > 0 and man["Demographic observations"] > 0 and man["Migration observations"] > 0
    assert man["Historical events"] > 0 and man["Policy evidence"] > 0 and man["Assumptions"] >= 1 and man["Evidence gaps"] > 0 and man["Life-stage baselines"] == 1
    assert d["manifest"]["readiness"]["overall"] == "NOT_READY"
    assert c.post(f"/snapshots/{s['id']}/refresh").status_code == 409
    # database-level immutability for Phase 5 records
    con = sqlite3.connect(srv.data_dir / "lifespan.db")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM snapshot_records WHERE snapshot_id = ?", (s["id"],))
    con.close()
    srv.restart()
    c = srv.client()
    after = c.get(f"/snapshots/{s['id']}").json()
    assert after["intact"] is True and after["contentHash"] == f["contentHash"]
    audits = c.get(f"/episodes/{EP}/audits").json()
    assert not any(x["title"] == "Finalized snapshot missing assumption record" for x in audits)
    v2 = c.post(f"/snapshots/{s['id']}/new-version").json()
    assert v2["version"] == 2
    diff = c.get("/snapshots/diff", params={"a": s["id"], "b": v2["id"]}).json()
    assert "records" in diff and all(r["kind"] in ("unchanged", "changed", "added", "removed") for r in diff["records"])


def test_audit_rules_national_as_city_and_prototype(srv):
    c = srv.client()
    _wpp(c)
    obs = c.get("/data/observations", params={"country": "IND", "indicator": "IMR"}).json()
    o = next(x for x in obs if x["year"] == 1970)
    r = c.post(f"/episodes/{EP}/facts/from-observations", json={"observationIds": [o["id"]]}).json()
    fid = r["factIds"][0]
    fact = next(x for x in c.get(f"/episodes/{EP}/facts").json() if x["id"] == fid)
    fact["region"] = "Delhi"
    assert c.put(f"/episodes/{EP}/facts/{fid}", json=fact).status_code == 200
    audits = c.get(f"/episodes/{EP}/audits").json()
    assert any(a["title"] == "National statistic represented as a city/regional fact" and fid in a["refs"] for a in audits)
    assert any(a["title"].startswith("Simulation readiness") for a in audits)


@pytest.mark.skipif(os.environ.get("LIFESPAN_LIVE_TESTS") != "1", reason="live network test (set LIFESPAN_LIVE_TESTS=1)")
def test_live_un_wpp(tmp_path):
    p = UNWPPProvider(cache_dir=tmp_path)
    res = p.fetch_many(["TFR", "LExMale"], ["IND", "ARE"], 2000, 2001)
    assert len(res.observations) == 8


@pytest.mark.skipif(os.environ.get("LIFESPAN_LIVE_TESTS") != "1", reason="live network test (set LIFESPAN_LIVE_TESTS=1)")
def test_live_world_bank_context_indicators():
    from app.providers.world_bank import WorldBankProvider
    res = WorldBankProvider().fetch_series("SE.PRM.ENRR", ["IN"], 1990, 1995)
    assert res.observations
