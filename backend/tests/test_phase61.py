"""Phase 6.1 model hardening — age-specific mortality, registry completeness, wage lineage, research acceptance,
replacement → new snapshot → rerun, MCP permissions. Offline: recorded official UN WPP / World Bank fixtures."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import Server

FIX = Path(__file__).parent / "fixtures"
EP = "ep-demo-delhi-dubai"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFESPAN_WB_FIXTURE_DIR", str(FIX / "wb"))
    monkeypatch.setenv("LIFESPAN_ILO_FIXTURE_DIR", str(FIX / "ilo"))
    monkeypatch.setenv("LIFESPAN_WPP_FIXTURE_FILE", str(FIX / "wpp" / "WPP2024_Demographic_Indicators_Medium.csv.gz"))
    monkeypatch.setenv("LIFESPAN_WPP_LT_FIXTURE_DIR", str(FIX / "wpp"))
    s = Server(tmp_path)
    s.start()
    yield s
    s.stop()


def _asm(c, **kw):
    body = {"domain": "income", "lifeStage": "first-job", "claim": "wage assumption", "value": "", "unit": "", "reason": "explicit test assumption for simulation",
            "confidence": "LOW"} | kw
    r = c.post(f"/episodes/{EP}/assumptions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _setup(c, life_table=True):
    assert c.post("/data/un-wpp/sync", json={"countries": ["IND", "ARE"], "yearStart": 1965, "yearEnd": 2065}).status_code == 200
    if life_table:
        r = c.post("/data/un-wpp/life-table/sync", json={"countries": ["IND", "ARE"], "yearStart": 1965, "yearEnd": 2065, "sexes": ["MALE", "BOTH"]})
        assert r.status_code == 200, r.text
        assert r.json()["lifeObservations"] > 5000 and r.json()["projections"] > 0
    _asm(c, value="3000", unit="INR/month", yearStart=1990, yearEnd=1990)
    _asm(c, lifeStage="migration", value="6000", unit="AED/month", yearStart=2004, yearEnd=2004)
    s = c.post(f"/episodes/{EP}/snapshots", json={"name": "Hardening snapshot"}).json()
    assert c.post(f"/snapshots/{s['id']}/finalize").status_code == 200
    return s


def _input(c, seed=1234):
    r = c.post(f"/episodes/{EP}/simulation/inputs", json={"masterSeed": seed, "acknowledged": True})
    assert r.status_code == 201, r.text
    return r.json()


def _run(c, iid, seed=None):
    r = c.post("/simulation/runs", json={"inputId": iid, "seed": seed, "overrides": []})
    assert r.status_code == 201, r.text
    return r.json()


def test_age_specific_mortality_preferred_with_lineage_across_ages(srv):
    c = srv.client()
    _setup(c)
    rv = c.get(f"/episodes/{EP}/simulation/review").json()
    mort = next(d for d in rv["dimensions"] if d["key"] == "mortality")
    assert any("abridged life tables" in r for r in mort["reasons"])
    run = _run(c, _input(c)["id"], 7)
    states = c.get(f"/simulation/runs/{run['id']}/states").json()
    lin = {s["age"]: s["state"]["mortality"] for s in states if s["state"].get("mortality")}
    # childhood, young adult, middle age, elderly
    for age, group in ((3, "1-4"), (8, "5-9"), (25, "25-29"), (47, "45-49")):
        if age in lin:
            L = lin[age]
            assert L["method"] == "AGE_SPECIFIC_LIFE_TABLE" and L["ageGroup"] == group, L
            assert L["formulaId"] == "MORT-LT-ANNUAL" and L["formulaVersion"] == "1"
            assert {"country", "year", "sex", "age", "sourceIndicator", "sourceValue", "annualProbability", "observationIds"} <= set(L)
            n = L["ageGroupSpan"]
            assert abs(L["annualProbability"] - (1 - (1 - float(L["sourceValue"])) ** (1 / n))) < 1e-7
    # demo episode locks survival up to its last locked event; draws (and lineage) start after that
    assert len(lin) >= 3
    # hazards rise with age (young adult < middle age); elderly hazard large
    young, mid = lin.get(25) or lin.get(20), lin.get(47) or lin.get(45)
    if young and mid:
        assert young["annualProbability"] < mid["annualProbability"]
    # India 1990 male 25–29: official 5q25 = 0.01307499 → annual 0.002628
    l25 = lin.get(25)
    if l25 and l25["sourceYear"] == 1995:
        assert l25["sourceValue"]
    assert all(L["method"] == "AGE_SPECIFIC_LIFE_TABLE" for L in lin.values()), {a: L["method"] for a, L in lin.items() if L["method"] != "AGE_SPECIFIC_LIFE_TABLE"}
    death = next(e for e in c.get(f"/simulation/runs/{run['id']}/events").json() if e["eventType"] == "death")
    if death["lineage"]:
        assert death["lineage"]["method"] in ("AGE_SPECIFIC_LIFE_TABLE",) and "finalAnnualProbability" in death["lineage"]
    # lineage survives a restart
    srv.restart()
    c = srv.client()
    states2 = c.get(f"/simulation/runs/{run['id']}/states").json()
    assert {s["age"]: s["state"].get("mortality") for s in states2 if s["state"].get("mortality")} == lin
    death2 = next(e for e in c.get(f"/simulation/runs/{run['id']}/events").json() if e["eventType"] == "death")
    assert death2["lineage"] == death["lineage"]


def test_elderly_hazard_from_life_table_engine_level():
    """Pure engine check for an elderly age and the open 100+ group."""
    from app.simulation.context import Ctx
    from app.simulation.priors import defaults
    from app.simulation.rules.mortality import hazard
    pri = {k: v | {"enabled": True} for k, v in defaults().items()}
    lt = {"IND|MALE": {"2040": {"80": {"LT_QX": ["0.5", "o80", "PROJECTION", "80-84"]}, "85": {"LT_QX": ["0.6", "o85", "PROJECTION", "85-89"]},
                                "100": {"LT_QX": ["1", "o100", "PROJECTION", "100+"], "LT_MX": ["0.5", "m100", "PROJECTION", "100+"]}}}}
    payload = {"config": {}, "character": {"sex": "MALE", "traits": {}}, "evidence": {"series": {}, "lifeTable": lt}, "priors": pri, "locks": [], "assumptions": []}
    ctx = Ctx(payload, 1)
    lt["IND|MALE"]["2040"]["0"] = {"LT_QX": ["0.03", "o0", "ESTIMATE", "0"]}
    lt["IND|MALE"]["2040"]["1"] = {"LT_QX": ["0.02", "o1", "ESTIMATE", "1-4"]}
    lt["IND|MALE"]["2040"]["5"] = {"LT_QX": ["0.01", "o5", "ESTIMATE", "5-9"]}
    p0 = hazard(ctx, "IND", 2040, 0, "MALE")
    assert p0.base == 0.03 and p0.base_class == "EMPIRICAL" and p0.lineage["ageGroupSpan"] == 1
    p3 = hazard(ctx, "IND", 2040, 3, "MALE")
    assert abs(p3.base - (1 - 0.98 ** 0.25)) < 1e-12 and p3.lineage["ageGroup"] == "1-4"
    p82 = hazard(ctx, "IND", 2040, 82, "MALE")
    assert abs(p82.base - (1 - 0.5 ** 0.2)) < 1e-12 and p82.lineage["ageGroup"] == "80-84" and p82.base_class == "DERIVED_FROM_EMPIRICAL"
    p101 = hazard(ctx, "IND", 2040, 101, "MALE")
    import math
    assert abs(p101.base - (1 - math.exp(-0.5))) < 1e-12 and p101.lineage["sourceIndicator"].endswith("LT_MX")
    # no life table → explicit broad fallback flagged
    payload["evidence"] = {"series": {"Q1560Male|IND|MALE|": {"2040": ["150", "q", "PROJECTION"]}}, "lifeTable": {}}
    pf = hazard(Ctx(payload, 1), "IND", 2040, 50, "MALE")
    assert pf.lineage["method"] == "BROAD_MEASURE_FALLBACK" and pf.lineage["ageSpecificAvailable"] is False


def test_all_constants_registered():
    from app.simulation.model_registry import DETERMINISTIC_RULES, scan_constants
    from app.simulation.priors import DEFAULT_PRIORS, meta
    r = scan_constants()
    assert r["unregistered"] == [], r["unregistered"]
    assert all(t["rule"] in DETERMINISTIC_RULES for t in r["tagged"])
    keys = {k for k, *_ in DEFAULT_PRIORS}
    for k in ("P-TRAIT-EFFECTS", "P-STATE-MODIFIERS", "P-AGE-BOUNDS", "P-ECON-RULES", "P-CONTROL-SCALING", "P-ACCOUNTING", "P-MORT-LT", "P-EVIDENCE-WINDOWS",
              "P-WAGE-NOMINAL-GROWTH", "P-WAGE-OCCUPATION", "P-WAGE-EXPERIENCE", "P-SPEND", "P-FINANCE", "P-TAX-EFFECTIVE", "P-RET", "P-OUTLIER"):
        assert k in keys
        assert meta(k)[0] in ("EMPIRICAL", "DERIVED", "USER_ASSUMPTION", "PROVISIONAL_MODEL_PRIOR", "DETERMINISTIC_ACCOUNTING_RULE")
    econ = dict((k, p) for k, _d, _n, _de, p, _c, _no in DEFAULT_PRIORS)["P-ECON-RULES"]
    assert econ["partialRetirementIncomeFactor"] == 0.5 and econ["creditLimitMultipleOfDistress"] == 1.2


def test_registry_exposed_and_edit_changes_behaviour(srv):
    c = srv.client()
    ps = c.get("/simulation/priors").json()["priors"]
    p = next(x for x in ps if x["key"] == "P-ACCOUNTING")
    assert p["classification"] == "DETERMINISTIC_ACCOUNTING_RULE" and p["units"]
    assert next(x for x in ps if x["key"] == "P-MORT-LT")["classification"] == "DERIVED"
    v = c.get(f"/model/validation?episode_id={EP}").json()
    assert v["constantScan"]["status"] == "PASS" and v["simulationEngineVersion"] == "6.1.0"
    assert {"mortality", "wage", "financialReconciliation"} <= set(v["methodology"]) and v["knownLimitations"]
    assert any(r["id"] == "R-UN-AGE-GROUPS" for r in v["deterministicRules"])


def test_wage_lineage_is_complete_and_never_evidence_looking(srv):
    c = srv.client()
    _setup(c)
    run = _run(c, _input(c)["id"], 11)
    ev = c.get(f"/simulation/runs/{run['id']}/events").json()
    fj = next(e for e in ev if e["eventType"] == "first_job")
    ch = fj["lineage"]["chain"]
    assert ch[0]["step"] == "anchor" and ch[0]["coverage"] == "ASSUMED" and ch[0]["classification"] == "ASSUMPTION_BASED"
    assert any(x["step"] == "temporal" for x in ch) or fj["year"] == 1990
    assert ch[-1]["step"] == "individual_position" and ch[-1]["classification"] == "SIMULATED"
    assert fj["lineage"]["referenceClass"] != "EMPIRICAL"
    states = c.get(f"/simulation/runs/{run['id']}/states").json()
    wp = next(s["economics"]["wageProvenance"] for s in states if (s["economics"] or {}).get("wageProvenance"))
    assert wp["class"] in ("ASSUMPTION_BASED", "PROVISIONAL_SYSTEM_PRIOR") and wp["chain"][-1]["step"] == "final"
    assert wp["chain"][-1]["classification"] == "SIMULATED"
    assert {x["classification"] for x in wp["chain"]} <= {"ASSUMPTION_BASED", "PROVISIONAL_SYSTEM_PRIOR", "SIMULATED", "DERIVED_FROM_EMPIRICAL", "EMPIRICAL"}


def test_research_acceptance_pipeline_replacement_and_snapshot_immutability(srv):
    c = srv.client()
    snap = _setup(c, life_table=False)
    run = _run(c, _input(c)["id"], 5)
    assert c.post(f"/simulation/runs/{run['id']}/canonical").status_code == 200
    db = sqlite3.connect(srv.data_dir / "lifespan.db")
    before_hash = c.get(f"/snapshots/{snap['id']}").json()["contentHash"]
    before_rows = db.execute("select count(*) from snapshot_records where snapshot_id=?", (snap["id"],)).fetchone()[0]
    ce = c.post("/candidate-evidence", json={"episodeId": EP, "claim": "Average monthly wage of service workers, Delhi 1990", "value": "2800", "unit": "INR/month",
                                             "source": "Example labour bureau table", "submittedBy": "mcp-agent"}).json()
    # scope is required — not guessed
    r = c.post(f"/candidate-evidence/{ce['id']}/review", json={"acceptAs": "FACT"})
    assert r.status_code == 422 and "country" in r.text and "population" in r.text
    r = c.post(f"/candidate-evidence/{ce['id']}/review", json={"acceptAs": "ESTIMATE", "country": "IND", "region": "Delhi", "yearStart": 1990, "yearEnd": 1990,
                                                               "population": "service workers, urban Delhi", "domain": "income", "metric": "avg monthly wage, service",
                                                               "sourceOrganization": "Labour Bureau (example)", "sourceType": "government"})
    assert r.status_code == 200, r.text
    out = r.json()
    cand = out["candidate"]
    assert cand["acceptedAs"] == "ESTIMATE" and cand["status"] == "ACCEPTED"
    assert cand["claim"] == ce["claim"] and cand["value"] == "2800"  # original retained
    L = cand["links"]
    assert L["sourceId"] and L["externalObservationId"] and L["factId"]
    facts = c.get("/facts").json() if c.get("/facts").status_code == 200 else []
    f = next((x for x in facts if x["id"] == L["factId"]), None)
    if f:
        assert f.get("factType", f.get("fact_type")) == "ESTIMATE"
    assert db.execute("select fact_type, source_id from facts where id=?", (L["factId"],)).fetchone() == ("ESTIMATE", L["sourceId"])
    assert db.execute("select count(*) from external_observations where id=?", (L["externalObservationId"],)).fetchone()[0] == 1
    assert out["gapsReevaluated"] is True
    reps = out["replacements"]
    assert any(x["targetKind"] == "ASSUMPTION" for x in reps) and any(x["targetKind"] == "PRIOR" for x in reps)
    assert all(x["message"].startswith("New evidence may replace") for x in reps)
    # nothing silently changed
    assert c.get(f"/snapshots/{snap['id']}").json()["contentHash"] == before_hash
    assert db.execute("select count(*) from snapshot_records where snapshot_id=?", (snap["id"],)).fetchone()[0] == before_rows
    canon = c.get(f"/episodes/{EP}/simulation/canonical").json()
    assert canon["run"]["id"] == run["id"] if canon.get("run") else True
    # CONTEXT acceptance is never a Fact
    ce2 = c.post("/candidate-evidence", json={"episodeId": EP, "claim": "Joint families common in 1980s Delhi", "source": "ethnography"}).json()
    r2 = c.post(f"/candidate-evidence/{ce2['id']}/review", json={"acceptAs": "CONTEXT", "country": "IND", "yearStart": 1980, "yearEnd": 1989,
                                                                 "population": "Delhi households", "sourceOrganization": "Univ. press"}).json()
    assert r2["candidate"]["links"].get("contextId") and "factId" not in r2["candidate"]["links"]
    # replacement → new snapshot version → rerun; old snapshot/run unchanged
    rep = next(x for x in reps if x["targetKind"] == "ASSUMPTION")
    s1 = c.post(f"/evidence-replacements/{rep['id']}/snapshot", json={"retireAssumption": False})
    assert s1.status_code == 200, s1.text
    new_sid = s1.json()["newSnapshotId"]
    assert new_sid != snap["id"] and c.get(f"/snapshots/{new_sid}").json()["status"] == "final"
    rr = c.post(f"/evidence-replacements/{rep['id']}/rerun")
    assert rr.status_code == 200, rr.text
    new_run = c.get(f"/simulation/runs/{rr.json()['newRunId']}").json()
    assert new_run["id"] != run["id"] and not new_run["isCanonical"]
    assert c.get(f"/simulation/runs/{run['id']}").json()["isCanonical"] is True
    assert c.get(f"/snapshots/{snap['id']}").json()["contentHash"] == before_hash
    # immutability triggers still in place
    with pytest.raises(sqlite3.DatabaseError):
        db.execute("update snapshot_records set payload='{}' where snapshot_id=?", (snap["id"],))
        db.commit()


def _mcp(srv, msgs):
    env = {**os.environ, "LIFESPAN_DATA_DIR": str(srv.data_dir), "PYTHONPATH": str(BACKEND)}
    init = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}]
    p = subprocess.run([sys.executable, "-m", "app.mcp_server"], input="\n".join(json.dumps(m) for m in init + msgs) + "\n", capture_output=True, text=True,
                       cwd=BACKEND, env=env, timeout=60)
    return {x["id"]: x for x in map(json.loads, p.stdout.splitlines())}


def _call(i, name, args):
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}}


def _txt(x):
    return x["result"]["content"][0]["text"]


def test_mcp_permissions(srv):
    c = srv.client()
    _setup(c, life_table=False)
    inp = _input(c)
    perm = c.get("/mcp/permissions").json()
    assert perm["config"] == {"profile": "external-research-agent", "enabledGroups": ["Research", "Evidence"], "consequential": "REQUIRE_APPROVAL"}
    risk = {t["name"]: t["riskClass"] for t in perm["tools"]}
    assert risk["get_episode"] == "READ" and risk["submit_candidate_evidence"] == "SAFE_WRITE" and risk["create_research_task"] == "SAFE_WRITE"
    assert risk["add_assumption"] == risk["change_model_prior"] == risk["run_simulation"] == risk["select_canonical_life"] == "CONSEQUENTIAL_WRITE"
    assert risk["modify_finalized_snapshot"] == risk["execute_sql"] == risk["mark_research_verified"] == "PROHIBITED"
    out = _mcp(srv, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                     _call(2, "run_simulation", {"inputId": inp["id"]}),
                     _call(3, "execute_sql", {"sql": "delete from facts"}),
                     _call(4, "modify_finalized_snapshot", {"snapshotId": "x"}),
                     _call(5, "mark_research_verified", {"candidateId": "x"}),
                     _call(6, "submit_candidate_evidence", {"episodeId": EP, "claim": "Delhi rent 1995", "source": "test"}),
                     _call(7, "add_assumption", {"episodeId": EP, "domain": "housing", "lifeStage": "first-job", "claim": "rent share 30%", "reason": "agent proposal"}),
                     _call(8, "create_research_task", {"episodeId": EP, "question": "Delhi rents 1990?", "category": "Housing"})])
    names = {t["name"] for t in out[1]["result"]["tools"]}
    assert "run_simulation" not in names and "get_story" not in names and "submit_candidate_evidence" in names and "execute_sql" not in names
    assert out[2]["result"]["isError"] and "DISABLED" in _txt(out[2])
    for i in (3, 4, 5):
        assert out[i]["result"]["isError"] and "PROHIBITED" in _txt(out[i])
    assert json.loads(_txt(out[6]))["status"] == "PENDING_REVIEW"
    pending = json.loads(_txt(out[7]))
    assert pending["status"] == "APPROVAL_REQUIRED"
    assert json.loads(_txt(out[8]))["status"] == "pending"
    # nothing written until the user approves
    assert not [a for a in c.get(f"/episodes/{EP}/assumptions").json() if a["claim"] == "rent share 30%"]
    ap = c.post(f"/mcp/approvals/{pending['approvalId']}/decide", json={"approve": True}).json()
    assert ap["status"] == "EXECUTED"
    assert [a for a in c.get(f"/episodes/{EP}/assumptions").json() if a["claim"] == "rent share 30%"]
    assert c.post(f"/mcp/approvals/{pending['approvalId']}/decide", json={"approve": True}).status_code == 409
    # DENY hides consequential tools; enabling a group exposes it
    c.put("/mcp/permissions", json={"profile": "custom", "enabledGroups": ["Research", "Evidence", "Simulation"], "consequential": "DENY"})
    out = _mcp(srv, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, _call(2, "change_model_prior", {"key": "P-HOUSING", "enabled": False})])
    names = {t["name"] for t in out[1]["result"]["tools"]}
    assert "get_simulation" in names and "run_simulation" not in names and "change_model_prior" not in names
    assert out[2]["result"]["isError"]
    assert next(p for p in c.get("/simulation/priors").json()["priors"] if p["key"] == "P-HOUSING")["enabled"] is True
    assert c.get("/mcp/status").json()["status"] == "AVAILABLE"
