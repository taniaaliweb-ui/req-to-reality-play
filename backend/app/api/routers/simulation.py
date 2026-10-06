"""Phase 6 endpoints: prior registry, simulation input review + frozen inputs, runs, events (See why),
Monte Carlo jobs, branching / what-if, canonical life, timeline integration, story, production, Life Receipt 2.0,
source appendix, exports / archive import, candidate evidence, research-task API, MCP and orchestration status.
No simulation logic lives here — routes call app.simulation services only."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import orchestration
from app.db import models as m
from app.db.database import SessionLocal, get_db
from app.services.repository import now_iso
from app.simulation import ENGINE_VERSION, inputs
from app.simulation import context as sim_ctx
from app.simulation import export as exp
from app.simulation import priors as pri
from app.simulation import product
from app.simulation import run as sim_run

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
IdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:@\-]{1,200}$")]


class In(BaseModel):
    model_config = {"extra": "forbid"}


def _ep(db: Session, eid: str) -> m.Episode:
    ep = db.get(m.Episode, eid)
    if ep is None:
        raise HTTPException(404, "Episode not found")
    return ep


def _err(fn, *a, **k):
    try:
        return fn(*a, **k)
    except LookupError as e:
        raise HTTPException(404, str(e).strip("'")) from e
    except (ValueError, inputs.InputError, sim_run.RunError, product.ProductError) as e:
        raise HTTPException(422, str(e)) from e


# ----------------------------------------------------------------- engine meta + priors
@router.get("/simulation/meta")
def meta():
    return {"engineVersion": ENGINE_VERSION, "priorLabel": pri.LABEL, "controls": sim_ctx.__doc__, "traitEffects": [
        {"trait": t, "affects": a, "effect": e} for t, a, e in sim_ctx.TRAIT_EFFECTS], "overrides": sorted(sim_run.OVERRIDE_TYPES),
        "batchSizes": [10, 25, 50, 100, 250, 500], "probabilityClasses": ["EMPIRICAL", "DERIVED_FROM_EMPIRICAL", "ASSUMPTION_BASED", "PROVISIONAL_SYSTEM_PRIOR", "DETERMINISTIC"]}


@router.get("/simulation/priors")
def list_priors(db: DB, include_history: bool = False):
    rows = db.scalars(select(m.SimulationPrior).order_by(m.SimulationPrior.domain, m.SimulationPrior.key, m.SimulationPrior.version.desc())) if include_history else pri.active(db)
    return {"label": pri.LABEL, "registryVersion": pri.registry_version([pri.prior_out(p) for p in pri.active(db)]), "priors": [pri.prior_out(p) for p in rows]}


class PriorPatch(In):
    parameter: dict[str, Any] | None = None
    enabled: bool | None = None
    notes: str | None = Field(None, max_length=4000)
    description: str | None = Field(None, max_length=4000)


@router.patch("/simulation/priors/{key}")
def patch_prior(key: IdPath, r: PriorPatch, db: DB):
    return pri.prior_out(_err(pri.update, db, key, now_iso(), parameter=r.parameter, enabled=r.enabled, notes=r.notes, description=r.description))


@router.get("/simulation/priors/{key}/history")
def prior_history(key: IdPath, db: DB):
    return [pri.prior_out(p) for p in pri.history(db, key)]


# ----------------------------------------------------------------- input review + frozen inputs
@router.get("/episodes/{eid}/simulation/review")
def input_review(eid: IdPath, db: DB, snapshot_id: str | None = None):
    _ep(db, eid)
    p = _err(inputs.assemble, db, eid, snapshot_id, None, 0)
    return {"snapshot": p["snapshot"], "config": p["config"], "locks": p["locks"], "assumptions": [{"id": a["id"], "domain": a["domain"], "claim": a["claim"],
            "value": a.get("value"), "unit": a.get("unit"), "parsed": a["parsed"]} for a in p["assumptions"]], **p["review"]}


class InputReq(In):
    snapshotId: str | None = None
    config: dict[str, int] | None = None
    masterSeed: int = Field(20260101, ge=0, le=2**31 - 1)
    acknowledged: bool = False


@router.post("/episodes/{eid}/simulation/inputs", status_code=201)
def create_input(eid: IdPath, r: InputReq, db: DB):
    _ep(db, eid)
    return inputs.input_out(_err(inputs.create, db, eid, r.snapshotId, r.config, r.masterSeed, r.acknowledged, now_iso()))


@router.get("/episodes/{eid}/simulation/inputs")
def list_inputs(eid: IdPath, db: DB):
    return [inputs.input_out(x) for x in db.scalars(select(m.SimulationInput).where(m.SimulationInput.episode_id == eid).order_by(m.SimulationInput.created_at.desc()))]


@router.get("/simulation/inputs/{iid}")
def get_input(iid: IdPath, db: DB, full: bool = False):
    return inputs.input_out(_err(sim_run.get_input, db, iid), full)


# ----------------------------------------------------------------- runs
class Override(In):
    type: str
    year: int | None = None
    fromYear: int | None = None
    age: int | None = None


class RunReq(In):
    inputId: str
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    overrides: list[Override] = []
    label: str = Field("", max_length=200)


@router.post("/simulation/runs", status_code=201)
def run_life(r: RunReq, db: DB):
    return sim_run.run_out(_err(sim_run.run_life, db, r.inputId, r.seed, [o.model_dump() for o in r.overrides], r.label))


@router.get("/episodes/{eid}/simulation/runs")
def list_runs(eid: IdPath, db: DB, kind: str | None = None, limit: int = Query(200, le=1000)):
    q = select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == eid)
    if kind:
        q = q.where(m.LifeSimulationRun.kind == kind)
    else:
        q = q.where(m.LifeSimulationRun.kind != "batch")
    out = []
    for x in db.scalars(q.order_by(m.LifeSimulationRun.started_at.desc()).limit(limit)):
        d = sim_run.run_out(x)
        d.pop("finalState")
        d.pop("economicSummary")
        out.append(d)
    return out


@router.get("/simulation/runs/{rid}")
def get_run(rid: IdPath, db: DB):
    r = db.get(m.LifeSimulationRun, rid)
    if r is None:
        raise HTTPException(404, "Run not found")
    return sim_run.run_out(r)


@router.post("/simulation/runs/{rid}/materialize")
def materialize(rid: IdPath, db: DB):
    r = db.get(m.LifeSimulationRun, rid)
    if r is None:
        raise HTTPException(404, "Run not found")
    return sim_run.run_out(_err(sim_run.materialize, db, r))


@router.get("/simulation/runs/{rid}/states")
def run_states(rid: IdPath, db: DB):
    return sim_run.load_states(db, rid)


@router.get("/simulation/runs/{rid}/events")
def run_events(rid: IdPath, db: DB, min_importance: int = 0):
    return sim_run.load_events(db, rid, min_importance)


class BranchReq(In):
    year: int
    overrides: list[Override] = []
    seed: int | None = None
    label: str = ""


@router.post("/simulation/runs/{rid}/branch", status_code=201)
def branch(rid: IdPath, r: BranchReq, db: DB):
    return sim_run.run_out(_err(sim_run.branch, db, rid, r.year, [o.model_dump() for o in r.overrides], r.seed, r.label))


@router.get("/simulation/compare")
def compare(a: str, b: str, db: DB):
    return _err(sim_run.compare, db, a, b)


@router.post("/simulation/runs/{rid}/canonical")
def set_canonical(rid: IdPath, db: DB):
    return sim_run.run_out(_err(sim_run.set_canonical, db, rid))


@router.get("/episodes/{eid}/simulation/canonical")
def canonical(eid: IdPath, db: DB):
    return sim_run.canonical_status(db, eid)


class RegenReq(In):
    seed: int = Field(..., ge=0, le=2**31 - 1)
    config: dict[str, int] | None = None
    acknowledged: bool = False


@router.post("/episodes/{eid}/simulation/regenerate", status_code=201)
def regenerate(eid: IdPath, r: RegenReq, db: DB):
    _ep(db, eid)
    return sim_run.run_out(_err(sim_run.regenerate_unlocked, db, eid, r.seed, r.config, r.acknowledged))


# ----------------------------------------------------------------- Monte Carlo jobs
class BatchReq(In):
    inputId: str
    runs: int


@router.post("/simulation/batches", status_code=202)
def start_batch(r: BatchReq, db: DB, wait: bool = False):
    return sim_run.job_out(_err(sim_run.start_batch, db, r.inputId, r.runs, SessionLocal, wait))


@router.get("/simulation/jobs/{jid}")
def get_job(jid: IdPath, db: DB):
    j = db.get(m.SimulationJob, jid)
    if j is None:
        raise HTTPException(404, "Job not found")
    db.refresh(j)
    return sim_run.job_out(j)


@router.get("/episodes/{eid}/simulation/jobs")
def list_jobs(eid: IdPath, db: DB):
    return [sim_run.job_out(j) for j in db.scalars(select(m.SimulationJob).where(m.SimulationJob.episode_id == eid).order_by(m.SimulationJob.created_at.desc()).limit(50))]


@router.post("/simulation/jobs/{jid}/cancel")
def cancel_job(jid: IdPath, db: DB):
    return sim_run.job_out(_err(sim_run.cancel_job, db, jid))


# ----------------------------------------------------------------- story / production / receipt / dashboard
@router.get("/episodes/{eid}/story-engine")
def get_story(eid: IdPath, db: DB, regenerate: bool = False):
    return _err(product.story, db, eid, regenerate)


@router.get("/episodes/{eid}/production-workspace")
def get_production(eid: IdPath, db: DB, regenerate: bool = False):
    return _err(product.production, db, eid, regenerate)


class ScriptReq(In):
    script: str = Field(..., max_length=500_000)


@router.put("/episodes/{eid}/production-workspace/script")
def put_script(eid: IdPath, r: ScriptReq, db: DB):
    return _err(product.save_script, db, eid, r.script)


@router.get("/episodes/{eid}/life-receipt")
def life_receipt(eid: IdPath, db: DB):
    return _err(product.receipt, db, eid)


@router.get("/episodes/{eid}/source-appendix")
def source_appendix(eid: IdPath, db: DB):
    return _err(product.appendix, db, eid)


@router.get("/episodes/{eid}/dashboard")
def dashboard(eid: IdPath, db: DB):
    _ep(db, eid)
    return product.dashboard(db, eid)


# ----------------------------------------------------------------- export / import
@router.get("/episodes/{eid}/export/archive")
def export_archive(eid: IdPath, db: DB):
    return _err(exp.export_archive, db, eid)


class ArchiveReq(In):
    archive: dict[str, Any]


@router.post("/archives/import", status_code=201)
def import_archive(r: ArchiveReq, db: DB):
    return _err(exp.import_archive, db, r.archive)


@router.get("/episodes/{eid}/export/ledger.csv", response_class=PlainTextResponse)
def export_csv(eid: IdPath, db: DB):
    c = sim_run.canonical(db, eid)
    if c is None:
        raise HTTPException(422, "No canonical life")
    return PlainTextResponse(exp.ledger_csv(sim_run.load_states(db, c.id)), media_type="text/csv")


def _bundle(db, eid):
    ep = _ep(db, eid)
    st = rc = scr = ap = None
    if sim_run.canonical(db, eid):
        st, rc, ap = product.story(db, eid), product.receipt(db, eid), product.appendix(db, eid)
        scr = product.production(db, eid)["script"]
    return ep.title, st, rc, scr, ap


@router.get("/episodes/{eid}/export/story.md", response_class=PlainTextResponse)
def export_md(eid: IdPath, db: DB):
    t, st, rc, scr, _ = _bundle(db, eid)
    return PlainTextResponse(exp.markdown(t, st, rc, scr), media_type="text/markdown")


@router.get("/episodes/{eid}/export/printable.html", response_class=HTMLResponse)
def export_html(eid: IdPath, db: DB):
    t, st, rc, scr, ap = _bundle(db, eid)
    return HTMLResponse(exp.printable_html(t, st, rc, scr, ap))


# ----------------------------------------------------------------- research interface (candidate evidence + tasks)
class CandidateIn(In):
    episodeId: str | None = None
    researchTaskId: str | None = None
    claim: str = Field(..., min_length=3, max_length=4000)
    value: str = Field("", max_length=120)
    unit: str = Field("", max_length=120)
    location: str = Field("", max_length=200)
    periodStart: int | None = Field(None, ge=1800, le=2100)
    periodEnd: int | None = Field(None, ge=1800, le=2100)
    source: str = Field(..., min_length=2, max_length=2000)
    url: str = Field("", max_length=2000)
    notes: str = Field("", max_length=4000)
    proposedType: str = Field("FACT", pattern=r"^(FACT|ESTIMATE|CONTEXT|POLICY|EVENT)$")
    submittedBy: str = Field("user", max_length=80)


def candidate_out(c: m.CandidateEvidence) -> dict:
    return {"id": c.id, "episodeId": c.episode_id, "researchTaskId": c.research_task_id, "claim": c.claim, "value": c.value, "unit": c.unit, "location": c.location,
            "periodStart": c.period_start, "periodEnd": c.period_end, "source": c.source, "url": c.url, "notes": c.notes, "proposedType": c.proposed_type,
            "submittedBy": c.submitted_by, "status": c.status, "reviewNote": c.review_note, "reviewedAt": c.reviewed_at, "createdAt": c.created_at}


def submit_candidate(db: Session, r: CandidateIn) -> m.CandidateEvidence:
    if r.episodeId and db.get(m.Episode, r.episodeId) is None:
        raise LookupError("Episode not found")
    c = m.CandidateEvidence(id="CE-" + uuid.uuid4().hex[:10], episode_id=r.episodeId, research_task_id=r.researchTaskId, claim=r.claim, value=r.value, unit=r.unit,
                            location=r.location, period_start=r.periodStart, period_end=r.periodEnd, source=r.source, url=r.url, notes=r.notes,
                            proposed_type=r.proposedType, submitted_by=r.submittedBy, status="PENDING_REVIEW", created_at=now_iso())
    db.add(c)
    db.commit()
    return c


@router.post("/candidate-evidence", status_code=201)
def post_candidate(r: CandidateIn, db: DB):
    return candidate_out(_err(submit_candidate, db, r))


@router.get("/candidate-evidence")
def list_candidates(db: DB, episode_id: str | None = None, status: str | None = None):
    q = select(m.CandidateEvidence)
    if episode_id:
        q = q.where(m.CandidateEvidence.episode_id == episode_id)
    if status:
        q = q.where(m.CandidateEvidence.status == status)
    return [candidate_full(c) for c in db.scalars(q.order_by(m.CandidateEvidence.created_at.desc()).limit(500))]


class ReviewReq(In):
    """Human review. acceptAs decides what the research becomes — acceptance never auto-classifies as FACT."""
    acceptAs: str = Field(..., pattern=r"^(FACT|ESTIMATE|CONTEXT|ASSUMPTION|REJECT)$")
    country: str = Field("", max_length=8)
    region: str = Field("", max_length=200)
    yearStart: int | None = Field(None, ge=1800, le=2100)
    yearEnd: int | None = Field(None, ge=1800, le=2100)
    population: str = Field("", max_length=500)
    value: str | None = Field(None, max_length=120)
    unit: str | None = Field(None, max_length=120)
    domain: str = Field("", max_length=40)
    metric: str = Field("", max_length=200)
    sex: str = Field("", max_length=10)
    lifeStage: str | None = Field(None, max_length=40)
    sourceTitle: str = Field("", max_length=2000)
    sourceOrganization: str = Field("", max_length=300)
    sourceType: str = Field("other", max_length=40)
    reliability: str = Field("Moderate", pattern=r"^(Primary|Strong|Moderate|Weak)$")
    url: str = Field("", max_length=2000)
    publicationDate: str = Field("", max_length=40)
    confidence: str = Field("medium", pattern=r"^(low|medium|high)$")
    note: str = Field("", max_length=4000)


def candidate_full(c: m.CandidateEvidence) -> dict:
    return candidate_out(c) | {"acceptedAs": c.accepted_as, "reviewedScope": c.reviewed_scope, "links": c.links or {}}


@router.post("/candidate-evidence/{cid}/review")
def review_candidate(cid: IdPath, r: ReviewReq, db: DB):
    from app.services import research_acceptance as ra
    try:
        res = ra.review(db, cid, r.model_dump())
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ra.AcceptanceError as e:
        raise HTTPException(422, str(e)) from e
    return {"candidate": candidate_full(res["candidate"]), "replacements": [ra.replacement_out(x) for x in res["replacements"]],
            "gapsReevaluated": res["gapsReevaluated"]}


@router.get("/episodes/{eid}/evidence-replacements")
def list_replacements(eid: IdPath, db: DB):
    from app.services import research_acceptance as ra
    return [ra.replacement_out(x) for x in db.scalars(select(m.EvidenceReplacement).where(m.EvidenceReplacement.episode_id == eid)
                                                      .order_by(m.EvidenceReplacement.created_at.desc()))]


class RepSnapReq(In):
    retireAssumption: bool = False


@router.post("/evidence-replacements/{rid}/snapshot")
def replacement_snapshot(rid: IdPath, r: RepSnapReq, db: DB):
    from app.services import research_acceptance as ra
    try:
        return ra.replacement_out(ra.replacement_snapshot(db, rid, r.retireAssumption))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ra.AcceptanceError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/evidence-replacements/{rid}/rerun")
def replacement_rerun(rid: IdPath, db: DB):
    from app.services import research_acceptance as ra
    try:
        return ra.replacement_out(ra.replacement_rerun(db, rid))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ra.AcceptanceError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/evidence-replacements/{rid}/dismiss")
def replacement_dismiss(rid: IdPath, db: DB):
    from app.services import research_acceptance as ra
    try:
        return ra.replacement_out(ra.dismiss(db, rid))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/research-api/tasks")
def research_tasks(db: DB, episode_id: str | None = None, status: str | None = "open"):
    q = select(m.ResearchTask)
    if episode_id:
        q = q.where(m.ResearchTask.episode_id == episode_id)
    if status:
        q = q.where(m.ResearchTask.status == status)
    gaps = select(m.EvidenceGap).where(m.EvidenceGap.status == "open")
    if episode_id:
        gaps = gaps.where(m.EvidenceGap.episode_id == episode_id)
    return {"tasks": [{"id": t.id, "episodeId": t.episode_id, "category": t.category, "question": t.question, "period": t.period, "status": t.status} for t in db.scalars(q)],
            "gaps": [{"id": g.id, "episodeId": g.episode_id, "title": g.title, "reason": g.reason, "priority": g.priority, "domain": g.domain} for g in db.scalars(gaps)],
            "submit": "POST /candidate-evidence (always PENDING_REVIEW; external agents cannot verify their own research)"}


# ----------------------------------------------------------------- MCP + orchestration status
@router.get("/mcp/status")
def mcp_status():
    from app import mcp_server
    return mcp_server.self_test()


class McpConfigReq(In):
    profile: str = Field("custom", max_length=40)
    enabledGroups: list[str] = []
    consequential: str = Field("REQUIRE_APPROVAL", pattern=r"^(REQUIRE_APPROVAL|ALLOW|DENY)$")


@router.get("/mcp/permissions")
def mcp_permissions(db: DB):
    from app import mcp_server
    cfg = mcp_server.get_config(db)
    return {"config": cfg, "tools": mcp_server.tool_catalogue(cfg), "groups": list(mcp_server.GROUPS), "riskClasses": list(mcp_server.RISK),
            "profiles": mcp_server.PROFILES}


@router.put("/mcp/permissions")
def put_mcp_permissions(r: McpConfigReq, db: DB):
    from app import mcp_server
    cfg = mcp_server.put_config(db, r.model_dump())
    return {"config": cfg, "tools": mcp_server.tool_catalogue(cfg), "groups": list(mcp_server.GROUPS), "riskClasses": list(mcp_server.RISK),
            "profiles": mcp_server.PROFILES}


@router.get("/mcp/approvals")
def mcp_approvals(db: DB):
    from app import mcp_server
    return [mcp_server.approval_out(a) for a in db.scalars(select(m.McpApproval).order_by(m.McpApproval.created_at.desc()).limit(200))]


class McpDecision(In):
    approve: bool


@router.post("/mcp/approvals/{aid}/decide")
def mcp_decide(aid: IdPath, r: McpDecision):
    from app import mcp_server
    try:
        return mcp_server.execute_approval(aid, r.approve)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/model/validation")
def model_validation(db: DB, episode_id: str | None = None):
    from app.simulation import validation
    return validation.report(db, episode_id)


@router.get("/orchestration/status")
def orch_status():
    return orchestration.status()


class AgentJobReq(In):
    role: str
    task: str = Field(..., max_length=4000)
    input: dict[str, Any] = {}
    parentId: str | None = None


@router.post("/orchestration/jobs", status_code=201)
def create_agent_job(r: AgentJobReq, db: DB):
    return orchestration.job_out(_err(orchestration.create_job, db, r.role, r.task, r.input, r.parentId))


@router.get("/orchestration/jobs")
def list_agent_jobs(db: DB):
    return [orchestration.job_out(j) for j in orchestration.list_jobs(db)]
