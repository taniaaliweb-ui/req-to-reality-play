"""Phase 6 — simulation engine, Monte Carlo, branching, canonical life, story, receipt, export/import, MCP.
Offline: real server + recorded UN WPP / World Bank fixtures; income comes from explicit assumptions."""
import json
import os
import sqlite3
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from tests.conftest import Server

FIX = Path(__file__).parent / "fixtures"
WPP = FIX / "wpp" / "WPP2024_Demographic_Indicators_Medium.csv.gz"
EP = "ep-demo-delhi-dubai"
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def srv(tmp_path, monkeypatch):
    monkeypatch.setenv("LIFESPAN_WB_FIXTURE_DIR", str(FIX / "wb"))
    monkeypatch.setenv("LIFESPAN_ILO_FIXTURE_DIR", str(FIX / "ilo"))
    monkeypatch.setenv("LIFESPAN_WPP_FIXTURE_FILE", str(WPP))
    s = Server(tmp_path)
    s.start()
    yield s
    s.stop()


def _asm(c, **kw):
    body = {"domain": "income", "lifeStage": "first-job", "claim": "x", "value": "", "unit": "", "reason": "explicit test assumption for simulation", "confidence": "LOW"} | kw
    r = c.post(f"/episodes/{EP}/assumptions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _setup(c, income=True):
    assert c.post("/data/un-wpp/sync", json={"countries": ["IND", "ARE"], "yearStart": 1965, "yearEnd": 2065}).status_code == 200
    if income:
        _asm(c, claim="Entry wage of a Delhi service worker", value="3000", unit="INR/month", yearStart=1990, yearEnd=1990)
        _asm(c, lifeStage="migration", claim="Dubai technician wage", value="6000", unit="AED/month", yearStart=2004, yearEnd=2004)
    s = c.post(f"/episodes/{EP}/snapshots", json={"name": "Sim test snapshot"}).json()
    assert c.post(f"/snapshots/{s['id']}/finalize").status_code == 200
    return s


def _input(c, seed=1234, ack=True):
    r = c.post(f"/episodes/{EP}/simulation/inputs", json={"masterSeed": seed, "acknowledged": ack})
    assert r.status_code == 201, r.text
    return r.json()


def _run(c, iid, seed=None, overrides=()):
    r = c.post("/simulation/runs", json={"inputId": iid, "seed": seed, "overrides": list(overrides)})
    assert r.status_code == 201, r.text
    return r.json()


def _sig(c, rid):
    ev = c.get(f"/simulation/runs/{rid}/events").json()
    st = c.get(f"/simulation/runs/{rid}/states").json()
    return [(e["year"], e["eventType"], e["probability"], e["randomDraw"], e["outcome"]) for e in ev], [(s["year"], s["country"], s["income"], s["netWorth"]) for s in st]


def test_missing_data_blocks_and_gate(srv):
    c = srv.client()
    _setup(c, income=False)
    rv = c.get(f"/episodes/{EP}/simulation/review").json()
    assert rv["canRun"] is False and any(b.startswith("Income") for b in rv["blocked"])
    dims = {d["key"]: d for d in rv["dimensions"]}
    assert dims["mortality"]["evidenceStatus"] in ("VERIFIED", "PARTIALLY VERIFIED")
    assert dims["housing"]["evidenceStatus"] == "MISSING" and dims["housing"]["simulationStatus"] == "PRIOR-COVERED"
    r = c.post(f"/episodes/{EP}/simulation/inputs", json={"masterSeed": 1, "acknowledged": True})
    assert r.status_code == 422 and "BLOCKED" in r.json()["detail"]
    # disabling a needed prior blocks the domain too
    assert c.patch("/simulation/priors/P-HOUSING", json={"enabled": False}).status_code == 200
    rv = c.get(f"/episodes/{EP}/simulation/review").json()
    assert any(b.startswith("Housing") for b in rv["blocked"])


def test_reproducibility_variation_restart_and_provenance(srv):
    c = srv.client()
    _setup(c)
    assert c.post(f"/episodes/{EP}/simulation/inputs", json={"masterSeed": 7, "acknowledged": False}).status_code == 422  # must acknowledge
    inp = _input(c)
    a = _run(c, inp["id"], 99)
    b = _run(c, inp["id"], 99)
    d = _run(c, inp["id"], 100)
    assert _sig(c, a["id"]) == _sig(c, b["id"])
    assert a["outcome"]["fingerprint"] == b["outcome"]["fingerprint"] != d["outcome"]["fingerprint"]
    srv.restart()
    c = srv.client()
    e = _run(c, inp["id"], 99)
    assert e["outcome"]["fingerprint"] == a["outcome"]["fingerprint"]
    # immutable input
    with sqlite3.connect(srv.data_dir / "lifespan.db") as con:
        with pytest.raises(sqlite3.DatabaseError):
            con.execute("UPDATE simulation_inputs SET master_seed = 1 WHERE id = ?", (inp["id"],))
    # probability trace: outcome ← draw ← final ← modifiers ← base ← evidence/assumption/prior
    ev = c.get(f"/simulation/runs/{a['id']}/events").json()
    stoch = [x for x in ev if x["probability"] is not None]
    assert len(stoch) > 5
    for x in stoch:
        assert x["probabilitySourceIds"] and x["probabilityClass"] in ("EMPIRICAL", "DERIVED_FROM_EMPIRICAL", "ASSUMPTION_BASED", "PROVISIONAL_SYSTEM_PRIOR")
        assert (x["randomDraw"] < x["probability"]) == (x["outcome"] == "OCCURRED")
        assert "Base:" in x["explanation"] and "Final probability" in x["explanation"]
    death = next(x for x in ev if x["eventType"] == "death")
    assert death["probabilityClass"] in ("DERIVED_FROM_EMPIRICAL", "EMPIRICAL") and any(i.startswith("LO:") for i in death["evidenceIds"])
    run = c.get(f"/simulation/runs/{a['id']}").json()
    assert not [x for x in run["audit"] if x["severity"] == "error"], run["audit"]
    assert run["qualityReport"]["economicConsistency"]["mismatches"] == 0 and "accuracy" not in json.dumps(run["qualityReport"]).lower().replace("no single accuracy", "")


def test_economics_reconcile_and_death_terminates(srv):
    c = srv.client()
    _setup(c)
    inp = _input(c)
    deaths = set()
    for seed in (1, 2, 3, 4, 5):
        r = _run(c, inp["id"], seed)
        st = c.get(f"/simulation/runs/{r['id']}/states").json()
        ev = c.get(f"/simulation/runs/{r['id']}/events").json()
        for s in st:
            for cur, rec in s["economics"]["reconciliation"].items():
                assert Decimal(rec["difference"]) == 0
                assert Decimal(rec["closing"]) == Decimal(rec["opening"]) + Decimal(rec["income"]) - Decimal(rec["expenses"]) + Decimal(rec["gains"]) + Decimal(rec["transfers"])
        d = next(x for x in ev if x["eventType"] == "death" and x["occurred"])
        assert st[-1]["year"] == d["year"] and all(x["seq"] <= d["seq"] or x["eventType"] == "estate" for x in ev)
        assert d["probability"] is not None  # hazard draw, not life expectancy
        deaths.add(d["age"])
    assert len(deaths) > 1


def test_locks_survive_rerun_restart_and_branch(srv):
    c = srv.client()
    tl = c.get("/timeline", params={"episode_id": EP}).json() if c.get("/timeline", params={"episode_id": EP}).status_code == 200 else []
    mig = next((e for e in tl if e["category"] == "Migration"), None)
    assert mig, "demo timeline should contain a migration event"
    mig["locked"] = True
    assert c.put(f"/timeline/{mig['id']}", json=mig).status_code in (200, 201)
    _setup(c)
    inp = _input(c)
    assert mig["id"] in inp["lockedTimelineEventIds"]
    r = _run(c, inp["id"], 5)
    ev = c.get(f"/simulation/runs/{r['id']}/events").json()
    forced = [x for x in ev if x["outcome"] == "FORCED" and mig["id"] in x["factIds"]]
    assert forced and forced[0]["year"] == mig["year"]
    srv.restart()
    c = srv.client()
    r2 = _run(c, inp["id"], 6)
    assert any(x["outcome"] == "FORCED" and mig["id"] in x["factIds"] for x in c.get(f"/simulation/runs/{r2['id']}/events").json())
    br = c.post(f"/simulation/runs/{r2['id']}/branch", json={"year": mig["year"] + 3, "overrides": [{"type": "no_marriage"}]}).json()
    assert any(x["outcome"] == "FORCED" and mig["id"] in x["factIds"] for x in c.get(f"/simulation/runs/{br['id']}/events").json())


def test_monte_carlo_branch_canonical_story_receipt_export(srv):
    c = srv.client()
    _setup(c)
    inp = _input(c, seed=4242)
    for n in (10, 50):
        j = c.post("/simulation/batches", params={"wait": "true"}, json={"inputId": inp["id"], "runs": n}).json()
        assert j["status"] == "COMPLETED" and j["done"] == n, j
        res = j["result"]
        assert res["runs"] == n and res["deathAge"]["n"] == n and "not a population forecast" in res["disclaimer"]
        assert set(res["representative"]) >= {"median", "strong", "weak", "unusual"}
    j2 = c.post("/simulation/batches", params={"wait": "true"}, json={"inputId": inp["id"], "runs": 10}).json()
    first = c.get(f"/simulation/runs/{res['memberRunIds'][0]}").json()
    again = c.get(f"/simulation/runs/{j2['result']['memberRunIds'][0]}").json()
    assert first["outcome"]["fingerprint"] == again["outcome"]["fingerprint"]  # reproducible from master seed
    # materialize a batch member (deterministic re-simulation)
    med = c.post(f"/simulation/runs/{res['representative']['median']}/materialize").json()
    assert med["economicSummary"]["years"] > 10
    # branch: migration vs no migration
    mig_run = None
    for rid in res["memberRunIds"]:
        o = c.get(f"/simulation/runs/{rid}").json()["outcome"]
        if o["migrated"]:
            mig_run = rid
            break
    assert mig_run, "at least one of 50 runs should migrate on the evidenced path"
    c.post(f"/simulation/runs/{mig_run}/materialize")
    mev = next(x for x in c.get(f"/simulation/runs/{mig_run}/events").json() if x["eventType"] == "migration" and x["occurred"])
    same = c.post(f"/simulation/runs/{mig_run}/branch", json={"year": mev["year"]}).json()
    assert same["outcome"]["fingerprint"] == c.get(f"/simulation/runs/{mig_run}").json()["outcome"]["fingerprint"]
    br = c.post(f"/simulation/runs/{mig_run}/branch", json={"year": mev["year"], "overrides": [{"type": "no_migration"}]}).json()
    cmp_ = c.get("/simulation/compare", params={"a": mig_run, "b": br["id"]}).json()
    assert cmp_["firstDivergentYear"] is None or cmp_["firstDivergentYear"] >= mev["year"]
    assert cmp_["outcomes"]["migrated"] == {"a": True, "b": False}
    pa = [s for s in c.get(f"/simulation/runs/{mig_run}/states").json() if s["year"] < mev["year"]]
    pb = [s for s in c.get(f"/simulation/runs/{br['id']}/states").json() if s["year"] < mev["year"]]
    assert pa == pb
    # canonical life + timeline integration
    can = c.post(f"/simulation/runs/{mig_run}/canonical").json()
    assert can["isCanonical"]
    tl = c.get("/timeline", params={"episode_id": EP}).json()
    assert any(e.get("simulationRunId") == mig_run for e in tl)
    srv.restart()
    c = srv.client()
    st = c.get(f"/episodes/{EP}/simulation/canonical").json()
    assert st["canonical"]["id"] == mig_run and st["stale"] is False
    # story
    story = c.get(f"/episodes/{EP}/story-engine").json()
    assert story["chapters"] and story["beats"] and story["label"].startswith("STRUCTURED LOCAL DRAFT")
    assert {"Birth & Family", "Migration", "Death"} <= {ch["title"] for ch in story["chapters"]}
    assert not [a for a in story["audit"] if a["severity"] == "error"], story["audit"]
    assert all(cl["refs"] or cl["type"] == "NARRATIVE_INTERPRETATION" for cl in story["claims"])
    # production + script editing
    prod = c.get(f"/episodes/{EP}/production-workspace").json()
    assert prod["scenes"] and prod["check"]["wordCount"] > 50 and not prod["check"]["warnings"]
    edited = c.put(f"/episodes/{EP}/production-workspace/script", json={"script": prod["script"] + "\nHe earned 987654321 in fact."}).json()
    assert edited["edited"] and any(w["ruleId"] == "unsupported-number" for w in edited["check"]["warnings"])
    # receipt agrees with the ledger
    rc = c.get(f"/episodes/{EP}/life-receipt").json()
    run = c.get(f"/simulation/runs/{mig_run}").json()
    states = c.get(f"/simulation/runs/{mig_run}/states").json()
    assert rc["ageAtDeath"] == run["outcome"]["deathAge"] == states[-1]["age"]
    for cur, v in rc["lifetimeNominalEarnings"].items():
        assert Decimal(v) == sum(Decimal(s["income"]) for s in states if s["currency"] == cur)
    assert rc["netWorthAtDeath"] == states[-1]["economics"]["netWorth"]
    assert rc["provenance"]["simulationSeed"] == run["seed"]
    # exports
    assert "SIMULATED" in c.get(f"/episodes/{EP}/export/ledger.csv").text
    assert "Print / Save as PDF" in c.get(f"/episodes/{EP}/export/printable.html").text
    assert "# " in c.get(f"/episodes/{EP}/export/story.md").text
    arc = c.get(f"/episodes/{EP}/export/archive").json()
    imp = c.post("/archives/import", json={"archive": arc}).json()
    nid = imp["episodeId"]
    assert nid != EP
    eps = {e["id"]: e for e in c.get("/episodes").json()}
    assert nid in eps and eps[nid]["character"]["name"] == eps[EP]["character"]["name"] and eps[nid]["character"]["birthYear"] == eps[EP]["character"]["birthYear"]
    st2 = c.get(f"/episodes/{nid}/simulation/canonical").json()
    assert st2["canonical"]["outcome"]["fingerprint"] == run["outcome"]["fingerprint"]
    assert c.get(f"/episodes/{nid}/life-receipt").json()["netWorthAtDeath"] == rc["netWorthAtDeath"]
    assert len([e for e in c.get("/timeline", params={"episode_id": nid}).json()]) == len(c.get("/timeline", params={"episode_id": EP}).json())
    assert [ch["title"] for ch in c.get(f"/episodes/{nid}/story-engine").json()["chapters"]] == [ch["title"] for ch in story["chapters"]]
    snaps_new = c.get(f"/episodes/{nid}/snapshots").json()
    assert snaps_new and all(s["status"] == "final" for s in snaps_new)
    facts_a = sorted((f["metric"], f["value"]) for f in c.get("/facts", params={"episode_id": EP}).json())
    facts_b = sorted((f["metric"], f["value"]) for f in c.get("/facts", params={"episode_id": nid}).json())
    assert facts_a == facts_b
    # bad archive version
    assert c.post("/archives/import", json={"archive": {**arc, "version": 99}}).status_code == 422


def test_mcp_real_client(srv, tmp_path):
    c = srv.client()
    _setup(c)
    inp = _input(c)
    st = c.get("/mcp/status").json()
    assert st["status"] == "AVAILABLE" and "run_simulation" in st["tools"]
    env = {**os.environ, "LIFESPAN_DATA_DIR": str(srv.data_dir), "PYTHONPATH": str(BACKEND)}
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_character", "arguments": {"episodeId": EP}}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "submit_candidate_evidence", "arguments": {"episodeId": EP, "claim": "Delhi rent 1995", "source": "test", "value": "900"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "run_simulation", "arguments": {"inputId": inp["id"], "seed": 3}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "update_snapshot", "arguments": {"snapshotId": "x"}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "submit_candidate_evidence", "arguments": {"claim": "x", "source": "y", "status": "ACCEPTED"}}}]
    p = subprocess.run([sys.executable, "-m", "app.mcp_server"], input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, cwd=BACKEND, env=env, timeout=60)
    out = {x["id"]: x for x in map(json.loads, p.stdout.splitlines())}
    assert out[1]["result"]["serverInfo"]["name"] == "lifespan"
    assert json.loads(out[2]["result"]["content"][0]["text"])["birthYear"]
    ce = json.loads(out[3]["result"]["content"][0]["text"])
    assert ce["status"] == "PENDING_REVIEW" and ce["submittedBy"] == "mcp-agent"
    run = json.loads(out[4]["result"]["content"][0]["text"])
    assert run["outcome"]["fingerprint"] == _run(c, inp["id"], 3)["outcome"]["fingerprint"]
    assert out[5]["result"]["isError"] and "forbidden" in out[5]["result"]["content"][0]["text"].lower()
    assert out[6]["result"]["isError"] or json.loads(out[6]["result"]["content"][0]["text"])["status"] == "PENDING_REVIEW"


def test_orchestration_is_not_configured(srv):
    c = srv.client()
    s = c.get("/orchestration/status").json()
    assert s["active"] is False and all(p["status"] == "DISCONNECTED" for p in s["providers"])
    j = c.post("/orchestration/jobs", json={"role": "RESEARCHER", "task": "find Delhi rent 1995"}).json()
    assert j["status"] == "QUEUED" and j["result"] is None and j["provider"] == "NOT_CONFIGURED"
