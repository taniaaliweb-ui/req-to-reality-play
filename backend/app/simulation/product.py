"""Story / production / receipt services built on the canonical run (shared by REST and MCP)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services.repository import now_iso
from app.simulation import run as sim_run
from app.simulation import story as eng


class ProductError(ValueError):
    pass


def _canonical_ctx(db: Session, eid: str):
    r = sim_run.canonical(db, eid)
    if r is None:
        raise ProductError("No canonical life yet — run a simulation and choose 'Set as Canonical Life' first.")
    inp = db.get(m.SimulationInput, r.input_id)
    return r, inp.payload, sim_run.load_states(db, r.id), sim_run.load_events(db, r.id)


def _artifact(db: Session, eid: str, kind: str) -> m.StoryArtifact | None:
    return db.scalar(select(m.StoryArtifact).where(m.StoryArtifact.episode_id == eid, m.StoryArtifact.kind == kind).order_by(m.StoryArtifact.created_at.desc()))


def _save(db, eid, run_id, kind, payload, edited=False):
    a = _artifact(db, eid, kind)
    ts = now_iso()
    if a is None or a.run_id != run_id:
        a = m.StoryArtifact(id=f"ART-{uuid.uuid4().hex[:10]}", episode_id=eid, run_id=run_id, kind=kind, payload=payload, edited=edited, created_at=ts, updated_at=ts)
        db.add(a)
    else:
        a.payload, a.edited, a.updated_at = payload, edited, ts
    db.commit()
    return a


def story(db: Session, eid: str, regenerate: bool = False) -> dict:
    r, payload, states, events = _canonical_ctx(db, eid)
    a = _artifact(db, eid, "story")
    if a is None or a.run_id != r.id or regenerate:
        st = eng.build(payload, sim_run.run_out(r), states, events)
        st["audit"] = eng.story_audit(st, payload, states, events)
        a = _save(db, eid, r.id, "story", st)
    return {**a.payload, "artifactId": a.id, "runId": a.run_id, "updatedAt": a.updated_at}


def production(db: Session, eid: str, regenerate: bool = False) -> dict:
    r, payload, states, events = _canonical_ctx(db, eid)
    st = story(db, eid)
    a = _artifact(db, eid, "production")
    if a is None or a.run_id != r.id or regenerate:
        tl = {f"{r.id}:{e.id.rsplit('-', 1)[1]}": e.id for e in db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.simulation_run_id == r.id))}
        a = _save(db, eid, r.id, "production", eng.production(st, sim_run.run_out(r), states, tl))
    p = a.payload
    return {**p, "artifactId": a.id, "runId": a.run_id, "edited": a.edited, "check": eng.script_check(p["script"], st, states)}


def save_script(db: Session, eid: str, script: str) -> dict:
    r, payload, states, events = _canonical_ctx(db, eid)
    cur = production(db, eid)
    p = {k: v for k, v in cur.items() if k not in ("artifactId", "runId", "edited", "check")}
    p["script"], p["scriptEdited"] = script, True
    _save(db, eid, r.id, "production", p, edited=True)
    return production(db, eid)


def receipt(db: Session, eid: str) -> dict:
    r, payload, states, events = _canonical_ctx(db, eid)
    return eng.receipt(payload, sim_run.run_out(r), states, events)


def appendix(db: Session, eid: str) -> dict:
    r, payload, states, events = _canonical_ctx(db, eid)
    snap_facts = [f.payload for f in db.scalars(select(m.SnapshotFact).where(m.SnapshotFact.snapshot_id == payload["snapshot"]["id"]))]
    src_ids = {f.get("sourceId") for f in snap_facts if f.get("sourceId")}
    sources = [{"id": s.id, "title": s.title, "organization": s.organization, "url": s.url} for s in (db.get(m.Source, i) for i in sorted(src_ids)) if s]
    return eng.source_appendix(payload, sim_run.run_out(r), states, events, snap_facts, sources)


def dashboard(db: Session, eid: str) -> dict:
    from app.simulation import inputs
    runs = list(db.scalars(select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == eid)))
    cs = sim_run.canonical_status(db, eid)
    snap = inputs.latest_final_snapshot(db, eid)
    st = _artifact(db, eid, "story")
    pr = _artifact(db, eid, "production")
    gaps = db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == eid, m.EvidenceGap.status == "open")).all()
    can = cs["canonical"]
    jobs = db.scalars(select(m.SimulationJob).where(m.SimulationJob.episode_id == eid).order_by(m.SimulationJob.created_at.desc()).limit(1)).all()
    return {"snapshot": snap and {"id": snap.id, "label": snap.label, "finalizedAt": snap.finalized_at},
            "simulationRuns": {"total": len(runs), "single": sum(1 for r in runs if r.kind in ("single", "what-if", "regenerate")), "batch": sum(1 for r in runs if r.kind == "batch"),
                               "branches": sum(1 for r in runs if r.kind == "branch")},
            "canonical": can and {"id": can["id"], "seed": can["seed"], "deathAge": can["outcome"].get("deathAge"), "stale": cs["stale"], "reasons": cs["reasons"]},
            "economicOutcome": can and {"netWorthAtDeath": can["outcome"].get("netWorthAtDeath"), "lifetimeEarnings": can["outcome"].get("lifetimeEarnings"),
                                        "position": can["outcome"].get("economicPosition")},
            "audit": can and {"errors": sum(1 for a in can["audit"] if a["severity"] == "error"), "warnings": sum(1 for a in can["audit"] if a["severity"] == "warning")},
            "story": st and {"chapters": len(st.payload["chapters"]), "beats": len(st.payload["beats"]), "auditIssues": len(st.payload.get("audit") or [])},
            "production": pr and {"scenes": len(pr.payload["scenes"]), "edited": pr.edited},
            "researchGaps": len(gaps), "latestJob": jobs and sim_run.job_out(jobs[0])}
