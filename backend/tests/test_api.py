from __future__ import annotations

DEMO = "ep-demo-delhi-dubai"


def _character(birth=1985):
    t = dict(ambition=50, aptitude=50, riskTolerance=50, discipline=50, socialSkills=50, financialDiscipline=50, resilience=50, familyAttachment=50, migrationWillingness=50)
    c = dict(realism=75, randomness=35, adversity=50, upwardMobility=50, downwardRisk=40)
    return {"id": "ch-test", "name": "Test", "country": "Nigeria", "region": "Lagos", "birthYear": birth, "gender": "female", "settlement": "urban",
            "startingClass": "working", "family": {"guardians": 2, "siblings": 1, "parentalIncomeClass": "working"}, "traits": t, "controls": c}


def _fail_count(c, eid):
    return sum(1 for a in c.get(f"/episodes/{eid}/audits").json() if a["category"] == "Fact" and a["outcome"] == "FAIL")


def test_1_health(server):
    r = server.client().get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "service": "lifespan-backend", "database": "connected", "databaseType": "sqlite"}


def test_2_demo_seed_once(server):
    server.restart()
    server.restart()
    eps = server.client().get("/episodes").json()
    assert [e["id"] for e in eps].count(DEMO) == 1
    assert len(eps) == 1
    # deleting demo and restarting must not resurrect or duplicate it
    server.client().delete(f"/episodes/{DEMO}")
    server.restart()
    assert server.client().get("/episodes").json() == []


def test_3_create_life_persists(server):
    c = server.client()
    r = c.post("/episodes", json={"id": "ep-lagos", "title": "Lagos 1985", "stage": "research", "character": _character()})
    assert r.status_code == 201, r.text
    assert c.get("/episodes/ep-lagos").json()["character"]["country"] == "Nigeria"
    server.restart()
    assert server.client().get("/episodes/ep-lagos").json()["title"] == "Lagos 1985"


def test_4_source_fact_audit(server):
    c = server.client()
    before = _fail_count(c, DEMO)
    assert before == 1  # F-013 ESTIMATE has no source in demo
    fact = c.get(f"/episodes/{DEMO}/facts/F-013").json()
    assert fact["sourceId"] is None
    r = c.patch(f"/episodes/{DEMO}/facts/F-013", json={"sourceId": "SRC-001"})
    assert r.status_code == 200
    assert _fail_count(c, DEMO) == 0
    # attaching a non-existent source is rejected (real relationship)
    assert c.put(f"/episodes/{DEMO}/facts/F-013", json={**fact, "sourceId": "SRC-NOPE"}).status_code == 422


def test_5_timeline_lock(server):
    c = server.client()
    assert c.get(f"/episodes/{DEMO}/timeline/E-05").json()["locked"] is False
    c.patch(f"/episodes/{DEMO}/timeline/E-05", json={"locked": True})
    assert c.get(f"/episodes/{DEMO}/timeline/E-05").json()["locked"] is True
    server.restart()
    assert server.client().get(f"/episodes/{DEMO}/timeline/E-05").json()["locked"] is True


def test_6_source_persistence(server):
    c = server.client()
    r = c.post("/sources", json={"title": "Test source", "type": "academic", "reliability": "Strong"})
    sid = r.json()["id"]
    c.put(f"/sources/{sid}", json={**r.json(), "title": "Edited source"})
    server.restart()
    assert server.client().get(f"/sources/{sid}").json()["title"] == "Edited source"


def test_7_timeline_crud(server):
    c = server.client()
    ev = {"id": "E-NEW", "year": 1999, "age": 29, "category": "Career", "title": "New job", "confidence": "low"}
    assert c.post(f"/episodes/{DEMO}/timeline", json=ev).status_code == 201
    c.patch(f"/episodes/{DEMO}/timeline/E-NEW", json={"title": "Edited job"})
    c.delete(f"/episodes/{DEMO}/timeline/E-02")
    server.restart()
    c = server.client()
    ids = {e["id"]: e for e in c.get(f"/episodes/{DEMO}/timeline").json()}
    assert ids["E-NEW"]["title"] == "Edited job"
    assert "E-02" not in ids


def test_8_story_persistence(server):
    c = server.client()
    ch = c.get(f"/episodes/{DEMO}/story/CH-2").json()
    c.put(f"/episodes/{DEMO}/story/CH-2", json={**ch, "text": "A persisted chapter."})
    server.restart()
    assert server.client().get(f"/episodes/{DEMO}/story/CH-2").json()["text"] == "A persisted chapter."


def test_validation_errors(server):
    c = server.client()
    bad = c.get(f"/episodes/{DEMO}/facts/F-001").json()
    assert c.put(f"/episodes/{DEMO}/facts/F-001", json={**bad, "factType": "RUMOUR"}).status_code == 422
    assert c.put(f"/episodes/{DEMO}/facts/F-001", json={**bad, "confidence": "certain"}).status_code == 422
    assert c.put(f"/episodes/{DEMO}/facts/F-001", json={**bad, "yearStart": 3000}).status_code == 422
    assert c.get("/episodes/nope").status_code == 404
    assert c.get("/episodes/bad%20id!").status_code == 422
    r = c.put(f"/episodes/{DEMO}/facts/F-001", json={**bad, "factType": "RUMOUR"})
    assert "Traceback" not in r.text


def test_import_no_overwrite(server):
    c = server.client()
    snap = c.get("/snapshot").json()
    snap["episodes"][0]["title"] = "CHANGED"
    r = c.post("/import", json={"data": snap, "overwrite": False}).json()
    assert r["created"] == 0 and r["skipped"] > 0
    assert c.get(f"/episodes/{DEMO}").json()["title"] != "CHANGED"
    r = c.post("/import", json={"data": snap, "overwrite": True}).json()
    assert r["updated"] > 0
    assert c.get(f"/episodes/{DEMO}").json()["title"] == "CHANGED"


def test_cors_local_only(server):
    c = server.client()
    ok = c.options("/health", headers={"Origin": "http://127.0.0.1:3000", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"
    bad = c.options("/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
