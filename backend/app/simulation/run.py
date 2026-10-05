"""Persistence and orchestration of simulation runs (single, Monte Carlo batch job, branch, what-if,
regenerate-unlocked, canonical life). API routes and the MCP server call ONLY these functions."""
from __future__ import annotations

import logging
import threading
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db import models as m
from app.services.repository import now_iso
from app.simulation import ENGINE_VERSION
from app.simulation import audit as sim_audit
from app.simulation import inputs, monte_carlo
from app.simulation import priors as pri
from app.simulation.engine import fingerprint, outcome, resume_state, simulate
from app.simulation.random import derive_seed
from app.simulation.rules import SimulationBlocked

log = logging.getLogger("lifespan.simulation")
OVERRIDE_TYPES = {"attends_university", "no_migration", "starts_business", "no_marriage", "retires_early"}
CATEGORY = {"migration": "Migration", "relationships": "Relationships", "fertility": "Family", "career": "Career", "education": "Education",
            "health": "Health", "mortality": "Health", "economics": "Finance", "housing": "Finance", "retirement": "Career", "historical": "External", "life": "Family"}


class RunError(ValueError):
    pass


def run_out(r: m.LifeSimulationRun) -> dict:
    return {"id": r.id, "episodeId": r.episode_id, "inputId": r.input_id, "seed": r.seed, "engineVersion": r.engine_version, "kind": r.kind, "status": r.status,
            "batchId": r.batch_id, "parentRunId": r.parent_run_id, "branchYear": r.branch_year, "overrides": r.overrides, "label": r.label,
            "outcome": r.outcome, "finalState": r.final_state, "economicSummary": r.economic_summary, "qualityReport": r.quality_report, "audit": r.audit,
            "isCanonical": r.is_canonical, "canonicalAt": r.canonical_at, "error": r.error, "startedAt": r.started_at, "completedAt": r.completed_at,
            "label_": "SIMULATED"}


def event_out(e: m.SimulationEvent) -> dict:
    return {"id": e.id, "runId": e.run_id, "seq": e.seq, "year": e.year, "age": e.age, "domain": e.domain, "eventType": e.event_type,
            "stateBefore": e.state_before, "stateAfter": e.state_after, "probability": None if e.probability is None else float(e.probability),
            "baseProbability": None if e.base_probability is None else float(e.base_probability), "probabilityClass": e.probability_class,
            "probabilitySourceIds": e.probability_source_ids, "factIds": e.fact_ids, "evidenceIds": e.evidence_ids, "assumptionIds": e.assumption_ids,
            "priorIds": e.prior_ids, "ruleId": e.rule_id, "ruleVersion": e.rule_version, "modifiers": e.modifiers,
            "randomDraw": None if e.random_draw is None else float(e.random_draw), "outcome": e.outcome, "occurred": e.occurred, "importance": e.importance,
            "explanation": e.explanation, "scenarioOverride": e.outcome == "SCENARIO_OVERRIDE", "label": "SIMULATED"}


def state_out(s: m.AnnualLifeState) -> dict:
    return {"year": s.year, "age": s.age, "country": s.country, "employment": s.employment_state, "currency": s.currency, "income": s.income,
            "netWorth": s.net_worth, "economics": s.state.get("economics"), "state": s.state.get("state")}


def _validate_overrides(ov: list[dict]) -> list[dict]:
    out = []
    for o in ov or []:
        if o.get("type") not in OVERRIDE_TYPES:
            raise RunError(f"Unknown scenario override {o.get('type')!r}. Allowed: {', '.join(sorted(OVERRIDE_TYPES))}")
        out.append({k: o[k] for k in ("type", "year", "fromYear", "age") if k in o and o[k] is not None} | {"label": "SCENARIO OVERRIDE"})
    return out


def _economic_summary(states: list[dict]) -> dict:
    return {"years": len(states), "currencies": sorted({c for s in states for c in s["economics"]["netWorth"]}),
            "ledger": [{"year": s["year"], "age": s["age"], "currency": s["currency"], "income": s["economics"]["totalIncome"],
                        "expenses": s["economics"]["totalExpenses"], "netWorth": s["economics"]["netWorth"]} for s in states]}


def store(db: Session, inp: m.SimulationInput, res: dict, *, kind: str, label: str = "", batch_id: str | None = None, parent_id: str | None = None,
          branch_year: int | None = None, overrides: list | None = None, full: bool = True, run_id: str | None = None) -> m.LifeSimulationRun:
    ts = now_iso()
    rid = run_id or "RUN-" + uuid.uuid4().hex[:10]
    au = sim_audit.audit_run(inp.payload, res["states"], res["events"])
    qr = sim_audit.quality_report(inp.payload, res["states"], res["events"], au)
    oc = {**res["outcome"], "fingerprint": fingerprint(res)}
    last = res["states"][-1]
    r = m.LifeSimulationRun(id=rid, episode_id=inp.episode_id, input_id=inp.id, seed=res["seed"], engine_version=ENGINE_VERSION, kind=kind, status="COMPLETED",
                            batch_id=batch_id, parent_run_id=parent_id, branch_year=branch_year, overrides=overrides or [], label=label,
                            final_state=last["state"], economic_summary=_economic_summary(res["states"]) if full else {"years": len(res["states"])},
                            outcome=oc, quality_report=qr, audit=au, started_at=ts, completed_at=now_iso())
    db.add(r)
    db.flush()
    write_details(db, r, res, full)
    return r


def write_details(db: Session, r: m.LifeSimulationRun, res: dict, full: bool) -> None:
    ts = now_iso()
    if full:
        db.add_all([m.AnnualLifeState(run_id=r.id, year=s["year"], age=s["age"], country=s["country"], employment_state=s["employment"], currency=s["currency"],
                                      income=s["income"], net_worth=s["netWorth"], state={"economics": s["economics"], "state": s["state"]}) for s in res["states"]])
    db.add_all([m.SimulationEvent(id=f"{r.id}:{e['seq']}", run_id=r.id, seq=e["seq"], year=e["year"], age=e["age"], domain=e["domain"], event_type=e["eventType"],
                                  state_before=e["stateBefore"], state_after=e["stateAfter"] or {}, probability=None if e["probability"] is None else str(e["probability"]),
                                  base_probability=None if e["baseProbability"] is None else str(e["baseProbability"]), probability_class=e["probabilityClass"],
                                  probability_source_ids=e["probabilitySourceIds"], fact_ids=e["factIds"], evidence_ids=e["evidenceIds"],
                                  assumption_ids=e["assumptionIds"], prior_ids=e["priorIds"], rule_id=e["ruleId"], rule_version=e["ruleVersion"],
                                  modifiers=e["modifiers"], random_draw=None if e["randomDraw"] is None else str(e["randomDraw"]), outcome=e["outcome"],
                                  occurred=e["occurred"], importance=e["importance"], explanation=e["explanation"], created_at=ts)
                for e in res["events"] if full or e["importance"] >= 2])


def get_input(db: Session, input_id: str) -> m.SimulationInput:
    inp = db.get(m.SimulationInput, input_id)
    if inp is None:
        raise LookupError("Simulation input not found")
    return inp


def _simulate(inp: m.SimulationInput, seed: int, overrides=None, start_state=None) -> dict:
    try:
        return simulate(inp.payload, seed, overrides, start_state)
    except SimulationBlocked as e:
        raise RunError(f"BLOCKED: {e}") from e


def run_life(db: Session, input_id: str, seed: int | None = None, overrides: list | None = None, label: str = "", kind: str = "single") -> m.LifeSimulationRun:
    inp = get_input(db, input_id)
    ov = _validate_overrides(overrides or [])
    seed = inp.master_seed if seed is None else seed
    r = store(db, inp, _simulate(inp, seed, ov), kind="what-if" if ov and kind == "single" else kind, label=label, overrides=ov)
    db.commit()
    return r


def load_states(db: Session, run_id: str) -> list[dict]:
    return [state_out(s) for s in db.scalars(select(m.AnnualLifeState).where(m.AnnualLifeState.run_id == run_id).order_by(m.AnnualLifeState.year))]


def load_events(db: Session, run_id: str, min_importance: int = 0) -> list[dict]:
    return [event_out(e) for e in db.scalars(select(m.SimulationEvent).where(m.SimulationEvent.run_id == run_id, m.SimulationEvent.importance >= min_importance)
                                             .order_by(m.SimulationEvent.seq))]


def materialize(db: Session, r: m.LifeSimulationRun) -> m.LifeSimulationRun:
    """Batch members store only outcome + meaningful events; re-simulate deterministically to store the full life,
    and prove the reproduction matches the stored fingerprint."""
    if db.scalar(select(m.AnnualLifeState.year).where(m.AnnualLifeState.run_id == r.id).limit(1)) is not None:
        return r
    if r.parent_run_id:
        raise RunError("Branch runs are always stored in full")
    inp = get_input(db, r.input_id)
    res = _simulate(inp, r.seed, r.overrides or None)
    if fingerprint(res) != r.outcome.get("fingerprint"):
        raise RunError("Reproduction mismatch — engine or input changed; refusing to materialize")
    db.execute(delete(m.SimulationEvent).where(m.SimulationEvent.run_id == r.id))
    write_details(db, r, res, True)
    r.economic_summary = _economic_summary(res["states"])
    db.commit()
    return r


def branch(db: Session, parent_id: str, year: int, overrides: list | None, seed: int | None = None, label: str = "") -> m.LifeSimulationRun:
    parent = db.get(m.LifeSimulationRun, parent_id)
    if parent is None:
        raise LookupError("Run not found")
    materialize(db, parent)
    inp = get_input(db, parent.input_id)
    states = load_states(db, parent.id)
    events = load_events(db, parent.id)
    if not states or not (states[0]["year"] < year <= states[-1]["year"]):
        raise RunError(f"Branch year must be within the parent's lifetime ({states[0]['year'] + 1}–{states[-1]['year']})")
    ov = _validate_overrides(overrides or [])
    start = resume_state(states, year)
    tail = _simulate(inp, parent.seed if seed is None else seed, (parent.overrides or []) + ov, start)
    pre_states = [s | {"income": s["income"], "netWorth": s["netWorth"]} for s in states if s["year"] < year]
    pre_events = [{"seq": e["seq"], "year": e["year"], "age": e["age"], "domain": e["domain"], "eventType": e["eventType"], "stateBefore": e["stateBefore"],
                   "stateAfter": e["stateAfter"], "probability": e["probability"], "baseProbability": e["baseProbability"], "probabilityClass": e["probabilityClass"],
                   "evidenceIds": e["evidenceIds"], "assumptionIds": e["assumptionIds"], "priorIds": e["priorIds"], "factIds": e["factIds"],
                   "probabilitySourceIds": e["probabilitySourceIds"], "modifiers": e["modifiers"], "randomDraw": e["randomDraw"], "ruleId": e["ruleId"],
                   "ruleVersion": e["ruleVersion"], "outcome": e["outcome"], "occurred": e["occurred"], "importance": e["importance"],
                   "explanation": e["explanation"]} for e in events if e["year"] < year]
    merged_events = pre_events + tail["events"]
    for i, e in enumerate(merged_events):
        e["seq"] = i
    merged = {"states": [{"year": s["year"], "age": s["age"], "country": s["country"], "employment": s["employment"], "currency": s["currency"],
                          "income": s["income"], "netWorth": s["netWorth"], "economics": s["economics"], "state": s["state"]} for s in pre_states] + tail["states"],
              "events": merged_events, "seed": tail["seed"]}
    merged["outcome"] = outcome(inp.payload, merged["states"], merged["events"])
    r = store(db, inp, merged, kind="branch", label=label or f"Branch at {year}", parent_id=parent.id, branch_year=year, overrides=(parent.overrides or []) + ov)
    db.commit()
    return r


def compare(db: Session, a_id: str, b_id: str) -> dict:
    A, B = load_states(db, a_id), load_states(db, b_id)
    ea, eb = load_events(db, a_id, 2), load_events(db, b_id, 2)
    by_a = {s["year"]: s for s in A}
    first_diff = next((s["year"] for s in B if s["year"] in by_a and (by_a[s["year"]]["netWorth"], by_a[s["year"]]["country"], by_a[s["year"]]["employment"])
                       != (s["netWorth"], s["country"], s["employment"])), None)
    ra, rb = db.get(m.LifeSimulationRun, a_id), db.get(m.LifeSimulationRun, b_id)
    keys = ("deathAge", "migrated", "children", "netWorthAtDeath", "lifetimeEarnings", "homeOwner", "businessSuccess", "retirementAge", "countries")
    return {"a": a_id, "b": b_id, "firstDivergentYear": first_diff,
            "identicalBefore": first_diff is None or all((by_a[s["year"]]["netWorth"], by_a[s["year"]]["country"]) == (s["netWorth"], s["country"]) for s in B if s["year"] < first_diff and s["year"] in by_a),
            "outcomes": {k: {"a": ra.outcome.get(k), "b": rb.outcome.get(k)} for k in keys},
            "eventsOnlyInA": [f"{e['year']} {e['eventType']}" for e in ea if e["occurred"] and not any((x["year"], x["eventType"]) == (e["year"], e["eventType"]) and x["occurred"] for x in eb)][:40],
            "eventsOnlyInB": [f"{e['year']} {e['eventType']}" for e in eb if e["occurred"] and not any((x["year"], x["eventType"]) == (e["year"], e["eventType"]) and x["occurred"] for x in ea)][:40]}


# ----------------------------------------------------------------- canonical life + timeline integration
def set_canonical(db: Session, run_id: str) -> m.LifeSimulationRun:
    r = db.get(m.LifeSimulationRun, run_id)
    if r is None:
        raise LookupError("Run not found")
    materialize(db, r)
    db.execute(update(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == r.episode_id).values(is_canonical=False))
    r.is_canonical, r.canonical_at = True, now_iso()
    db.execute(delete(m.TimelineEvent).where(m.TimelineEvent.episode_id == r.episode_id, m.TimelineEvent.simulation_run_id.is_not(None)))
    ts = now_iso()
    inp = get_input(db, r.input_id)
    for e in load_events(db, r.id, 3):
        if not e["occurred"] or e["outcome"] == "FORCED" or e["eventType"] in ("birth",):
            continue
        cat = CATEGORY.get(e["domain"], "External")
        if e["domain"] == "outliers":
            cat = "Negative outlier" if e["eventType"] == "major_asset_loss" else "Positive outlier"
        if e["eventType"] in ("job_loss", "business_failure"):
            cat = "Career"
        loc = (e["stateAfter"] or {}).get("country") or next((s["country"] for s in load_states(db, r.id) if s["year"] == e["year"]), "")
        db.add(m.TimelineEvent(id=f"SIMTL-{r.id}-{e['seq']}", episode_id=r.episode_id, year=e["year"], age=e["age"], location=loc, category=cat,
                               title=e["eventType"].replace("_", " ").capitalize() + (" (scenario override)" if e["scenarioOverride"] else ""),
                               description=e["explanation"].split("\n")[0], financial_effect="", emotions=[], confidence="low", fact_ids=[],
                               simulation_reason=f"SIMULATED by run {r.id} (seed {r.seed}, engine {r.engine_version}, input {inp.id}). " + e["explanation"][:1500],
                               locked=False, simulation_run_id=r.id, created_at=ts, updated_at=ts))
    db.commit()
    return r


def canonical(db: Session, episode_id: str) -> m.LifeSimulationRun | None:
    return db.scalar(select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == episode_id, m.LifeSimulationRun.is_canonical.is_(True)))


def canonical_status(db: Session, episode_id: str) -> dict:
    r = canonical(db, episode_id)
    if r is None:
        return {"canonical": None, "stale": False, "reasons": []}
    inp = get_input(db, r.input_id)
    reasons = []
    snap = inputs.latest_final_snapshot(db, episode_id)
    if snap and snap.id != inp.dataset_snapshot_id:
        reasons.append(f"newer finalized snapshot '{snap.label}'")
    act = [pri.prior_out(p) for p in pri.active(db)]
    if pri.registry_version(act) != inp.prior_registry_version:
        reasons.append("prior registry changed")
    if r.engine_version != ENGINE_VERSION:
        reasons.append(f"engine {r.engine_version} → {ENGINE_VERSION}")
    ep = db.get(m.Episode, episode_id)
    if ep and ep.character and inputs.character_version(inputs._character(ep.character)) != inp.character_version:
        reasons.append("Character DNA changed")
    locks = sorted(e.id for e in db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.episode_id == episode_id, m.TimelineEvent.locked.is_(True))))
    if locks != sorted(inp.locked_timeline_event_ids):
        reasons.append("locked timeline events changed")
    return {"canonical": run_out(r), "stale": bool(reasons), "reasons": reasons,
            "message": "Canonical life was created using an older simulation configuration." if reasons else "Canonical life matches the current configuration."}


def regenerate_unlocked(db: Session, episode_id: str, seed: int, config: dict | None, acknowledged: bool) -> m.LifeSimulationRun:
    """Preserve locked events → construct a new SimulationInput → simulate a compatible life → store as a new run."""
    prev = canonical(db, episode_id)
    inp = inputs.create(db, episode_id, None, config or (get_input(db, prev.input_id).config if prev else None), seed, acknowledged, now_iso())
    return run_life(db, inp.id, seed, label="Regenerated (locked events preserved)", kind="regenerate")


# ----------------------------------------------------------------- background Monte Carlo jobs (no Redis/Celery)
_threads: dict[str, threading.Thread] = {}


def job_out(j: m.SimulationJob) -> dict:
    return {"id": j.id, "episodeId": j.episode_id, "kind": j.kind, "status": j.status, "total": j.total, "done": j.done, "params": j.params,
            "result": j.result, "error": j.error, "createdAt": j.created_at, "startedAt": j.started_at, "completedAt": j.completed_at,
            "progress": round(j.done / j.total, 4) if j.total else 0}


def start_batch(db: Session, input_id: str, n: int, session_factory, wait: bool = False) -> m.SimulationJob:
    if n not in (10, 25, 50, 100, 250, 500):
        raise RunError("Batch size must be one of 10, 25, 50, 100, 250, 500")
    inp = get_input(db, input_id)
    j = m.SimulationJob(id="JOB-" + uuid.uuid4().hex[:10], episode_id=inp.episode_id, kind="monte-carlo", status="QUEUED", total=n, done=0,
                        params={"inputId": input_id, "runs": n, "masterSeed": inp.master_seed}, created_at=now_iso())
    db.add(j)
    db.commit()
    t = threading.Thread(target=_batch_worker, args=(j.id, session_factory), daemon=True)
    _threads[j.id] = t
    t.start()
    if wait:
        t.join()
        db.refresh(j)
    return j


def _batch_worker(job_id: str, session_factory) -> None:
    with session_factory() as db:
        j = db.get(m.SimulationJob, job_id)
        j.status, j.started_at = "RUNNING", now_iso()
        db.commit()
        try:
            inp = get_input(db, j.params["inputId"])
            members = []
            for i in range(j.total):
                db.refresh(j)
                if j.cancel_requested:
                    j.status = "CANCELLED"
                    break
                seed = derive_seed(inp.master_seed, i)
                res = _simulate(inp, seed)
                r = store(db, inp, res, kind="batch", label=f"Outcome #{i + 1}", batch_id=j.id, full=False)
                members.append((r.id, r.outcome))
                j.done = i + 1
                if (i + 1) % 5 == 0 or i + 1 == j.total:
                    db.commit()
            db.commit()
            j.result = monte_carlo.summarize(members) | {"memberRunIds": [rid for rid, _ in members], "masterSeed": inp.master_seed}
            if j.status != "CANCELLED":
                j.status = "COMPLETED"
        except Exception as e:  # recorded, never hidden
            log.exception("batch failed")
            db.rollback()
            j = db.get(m.SimulationJob, job_id)
            j.status, j.error = "FAILED", str(e)[:2000]
        j.completed_at = now_iso()
        db.commit()


def cancel_job(db: Session, job_id: str) -> m.SimulationJob:
    j = db.get(m.SimulationJob, job_id)
    if j is None:
        raise LookupError("Job not found")
    if j.status in ("QUEUED", "RUNNING"):
        j.cancel_requested = True
        db.commit()
    return j


def recover_jobs(db: Session) -> None:
    for j in db.scalars(select(m.SimulationJob).where(m.SimulationJob.status.in_(["QUEUED", "RUNNING"]))):
        j.status, j.error, j.completed_at = "FAILED", "Interrupted by backend restart — re-run the batch (results are reproducible from the master seed).", now_iso()
    db.commit()
