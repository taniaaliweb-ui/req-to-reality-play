"""Phase 5 endpoints: UN WPP, life-context observations, policy / historical / qualitative registries,
Life Evidence Matrix, readiness 2.0, life gaps, life-stage baselines, assumption register and
migration-path evidence. React reaches these only via lifespanApi.ts."""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import providers
from app.db import models as m
from app.db.database import get_db
from app.providers.base import ProviderError
from app.providers.un_wpp import METRICS as WPP_METRICS
from app.services import labor
from app.services import life_context as life
from app.services import repository as repo
from app.services import truth

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
IdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:\-]{1,200}$")]
Country3 = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")]
Year = Annotated[int, Field(ge=1800, le=2100)]
Conf = Literal["HIGH", "MEDIUM", "LOW"]


class In(BaseModel):
    model_config = {"populate_by_name": True, "extra": "forbid"}


def _ep(db: Session, eid: str) -> m.Episode:
    ep = db.get(m.Episode, eid)
    if ep is None:
        raise HTTPException(404, "Episode not found")
    return ep


def _required(db: Session) -> list[str]:
    return list(repo.get_settings(db).get("simulationRequiredDomains") or [])


@router.get("/life/meta")
def meta():
    return {"stages": [{"key": k, "label": lbl, "critical": c, "other": o} for k, lbl, c, o in life.STAGES], "domains": life.DATA_DOMAINS,
            "matrixDomains": [{"key": k, "label": v} for k, v, _ in life.MATRIX_DOMAINS],
            "readinessGroups": [{"key": k, "label": v, "domains": d} for k, v, d in life.READINESS_GROUPS],
            "validityWindows": [{"domain": k, "years": v, "reason": life.WINDOW_REASON.get(k, "")} for k, v in life.VALIDITY_WINDOW.items()],
            "wppIndicators": [{"code": k, "name": v.name, "unit": v.unit, "domain": v.domain} for k, v in WPP_METRICS.items()],
            "importHeader": life.IMPORT_HEADER, "futureHooks": life.FUTURE_HOOKS}


# ------------------------------------------------------------ UN WPP
class WppSync(In):
    indicators: list[str] = Field(default_factory=list, max_length=40)
    countries: list[Country3] = Field(min_length=1, max_length=20)
    yearStart: Year
    yearEnd: Year


@router.post("/data/un-wpp/sync")
def sync_wpp(db: DB, req: WppSync):
    st = repo.get_settings(db)
    if not (st["externalDataEnabled"] and st.get("unWppEnabled", True)):
        raise HTTPException(403, "UN WPP access is disabled in Settings.")
    if req.yearEnd < req.yearStart:
        raise HTTPException(422, "yearEnd must be >= yearStart")
    p = providers.get_un_wpp()
    started = repo.now_iso()
    inds = req.indicators or list(WPP_METRICS)
    try:
        res = p.fetch_many(inds, req.countries, req.yearStart, req.yearEnd)
    except ProviderError as e:
        summary = {"error": f"{e.kind}: {e}", "retrieved": 0, "unavailable": None}
        db.add(m.ProviderSync(id="SYNC-" + uuid.uuid4().hex[:10], provider="un-wpp", started_at=started, finished_at=repo.now_iso(), status="error",
                              request=req.model_dump(), summary=summary))
        db.commit()
        raise HTTPException(502, f"UN WPP: {e}") from e
    counts = truth.store_observations(db, res.observations)
    db.flush()
    n = life.normalize_un_wpp(db, res.observations)
    proj = sum(1 for o in res.observations if o.raw.get("projection"))
    status = "partial" if res.missing or res.countries_unknown else "ok"
    summary = {"retrieved": len(res.observations), "projections": proj, "lifeObservations": n, "unavailable": len(res.missing), "missing": res.missing[:200],
               "unknownCountries": res.countries_unknown, **counts}
    db.add(m.ProviderSync(id="SYNC-" + uuid.uuid4().hex[:10], provider="un-wpp", started_at=started, finished_at=repo.now_iso(), status=status,
                          request=req.model_dump(), summary=summary))
    db.commit()
    return {"provider": "un-wpp", "status": status, "startedAt": started, "finishedAt": repo.now_iso(), **summary}


# ------------------------------------------------------------ observations
@router.get("/life/observations")
def list_obs(db: DB, domain: str | None = None, country: str | None = None, metric: str | None = None, yearStart: int | None = None,
             yearEnd: int | None = None, provider: str | None = None, limit: Annotated[int, Query(ge=1, le=5000)] = 1000):
    L = m.LifeObservation
    q = select(L)
    for col, v in ((L.domain, domain), (L.country, country and country.upper()), (L.metric, metric), (L.provider, provider)):
        if v:
            q = q.where(col == v)
    if yearStart is not None:
        q = q.where(L.year >= yearStart)
    if yearEnd is not None:
        q = q.where(L.year <= yearEnd)
    return [life.life_obs_out(r) for r in db.scalars(q.order_by(L.domain, L.country, L.metric, L.year).limit(limit))]


@router.get("/life/observations/summary")
def obs_summary(db: DB):
    L = m.LifeObservation
    rows = db.execute(select(L.domain, L.country, L.provider, func.count(), func.min(L.year), func.max(L.year)).group_by(L.domain, L.country, L.provider)).all()
    return [{"domain": d, "country": c, "provider": p, "count": n, "yearMin": a, "yearMax": b} for d, c, p, n, a, b in rows]


class LifeImport(In):
    provider: Literal["manual", "india-mospi", "uae-fcsc"]
    csv: str = Field(min_length=1, max_length=5_000_000)


@router.post("/life/import/preview")
def import_preview(req: LifeImport):
    out = life.parse_life_import(req.csv, req.provider)
    out["rows"] = out["rows"][:500]
    return out


@router.post("/life/import/commit")
def import_commit(db: DB, req: LifeImport):
    p = providers.IMPORT_PROVIDERS[req.provider]
    return life.commit_life_import(db, req.csv, req.provider, p.provider_name or req.provider)


# ------------------------------------------------------------ registries
class PolicyIn(In):
    country: Country3
    policyType: Literal["work-visa", "residency", "citizenship", "family-sponsorship", "retirement", "pension", "labour-law", "emigration", "other"]
    title: str = Field(min_length=3, max_length=400)
    effectiveStart: str = Field(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")
    effectiveEnd: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")
    description: str = ""
    source: str = Field(min_length=3)
    sourceOrganization: str = Field(min_length=2)
    sourceUrl: str = ""
    factType: Literal["FACT", "CONTEXT"] = "FACT"
    confidence: Conf = "MEDIUM"
    verification: Literal["unverified", "verified"] = "unverified"
    notes: str = ""


def _apply_policy(p: m.PolicyEvidence, r: PolicyIn):
    p.country, p.policy_type, p.title, p.effective_start, p.effective_end = r.country.upper(), r.policyType, r.title, r.effectiveStart, r.effectiveEnd
    p.description, p.source, p.source_organization, p.source_url = r.description, r.source, r.sourceOrganization, r.sourceUrl
    p.fact_type, p.confidence, p.verification, p.notes, p.updated_at = r.factType, r.confidence, r.verification, r.notes, repo.now_iso()


@router.get("/life/policies")
def list_policies(db: DB, country: str | None = None):
    q = select(m.PolicyEvidence)
    if country:
        q = q.where(m.PolicyEvidence.country == country.upper())
    return [life.policy_out(p) for p in db.scalars(q.order_by(m.PolicyEvidence.country, m.PolicyEvidence.effective_start))]


@router.post("/life/policies", status_code=201)
def create_policy(db: DB, r: PolicyIn):
    ts = repo.now_iso()
    p = m.PolicyEvidence(id="POL-" + uuid.uuid4().hex[:8], created_at=ts, updated_at=ts)
    _apply_policy(p, r)
    db.add(p)
    db.commit()
    return life.policy_out(p)


@router.put("/life/policies/{pid}")
def update_policy(pid: IdPath, db: DB, r: PolicyIn):
    p = db.get(m.PolicyEvidence, pid)
    if p is None:
        raise HTTPException(404, "Policy not found")
    _apply_policy(p, r)
    db.commit()
    return life.policy_out(p)


@router.delete("/life/policies/{pid}", status_code=204)
def delete_policy(pid: IdPath, db: DB):
    p = db.get(m.PolicyEvidence, pid)
    if p is None:
        raise HTTPException(404, "Policy not found")
    db.delete(p)
    db.commit()


class EventIn(In):
    name: str = Field(min_length=3, max_length=300)
    category: Literal["recession", "currency-crisis", "war", "pandemic", "oil-shock", "financial-crisis", "policy-change", "migration-event", "technology", "natural-disaster", "other"]
    geography: list[str] = Field(min_length=1, max_length=40)
    region: str | None = None
    startDate: str = Field(pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")
    endDate: str | None = Field(default=None, pattern=r"^\d{4}(-\d{2}(-\d{2})?)?$")
    economicRelevance: Conf = "MEDIUM"
    description: str = ""
    sources: list[dict] = Field(min_length=1)
    verification: Literal["unverified", "verified"] = "unverified"


@router.get("/life/events")
def list_events(db: DB):
    return [life.event_out(e) for e in db.scalars(select(m.HistoricalEvent).order_by(m.HistoricalEvent.start_date))]


@router.post("/life/events", status_code=201)
def create_event(db: DB, r: EventIn):
    ts = repo.now_iso()
    e = m.HistoricalEvent(id="EV-" + uuid.uuid4().hex[:8], name=r.name, category=r.category, geography=[g.upper() for g in r.geography], region=r.region or None,
                          start_date=r.startDate, end_date=r.endDate, economic_relevance=r.economicRelevance, description=r.description, sources=r.sources,
                          verification=r.verification, created_at=ts, updated_at=ts)
    db.add(e)
    db.commit()
    return life.event_out(e)


@router.post("/life/events/{evid}/verify")
def verify_event(evid: IdPath, db: DB, verified: bool = True):
    e = db.get(m.HistoricalEvent, evid)
    if e is None:
        raise HTTPException(404, "Event not found")
    e.verification, e.updated_at = ("verified" if verified else "unverified"), repo.now_iso()
    db.commit()
    return life.event_out(e)


@router.post("/life/policies/{pid}/verify")
def verify_policy(pid: IdPath, db: DB, verified: bool = True):
    p = db.get(m.PolicyEvidence, pid)
    if p is None:
        raise HTTPException(404, "Policy not found")
    p.verification, p.updated_at = ("verified" if verified else "unverified"), repo.now_iso()
    db.commit()
    return life.policy_out(p)


@router.delete("/life/events/{evid}", status_code=204)
def delete_event(evid: IdPath, db: DB):
    e = db.get(m.HistoricalEvent, evid)
    if e is None:
        raise HTTPException(404, "Event not found")
    db.delete(e)
    db.commit()


@router.get("/episodes/{eid}/life/events")
def episode_events(eid: IdPath, db: DB):
    _ep(db, eid)
    plan = life.stage_plan(db, eid)
    out = []
    for e in db.scalars(select(m.HistoricalEvent).order_by(m.HistoricalEvent.start_date)):
        matches = []
        for s in plan["stages"]:
            if not s["applicable"]:
                continue
            ys = range(s["yearStart"], s["yearEnd"] + 1)
            best = None
            for y in ys:
                c, ct = plan["loc"](y)
                r = life.event_relevance(e, c, ct, s["yearStart"], s["yearEnd"])
                if r["relevance"] == "RELEVANT":
                    best = r
                    break
                if r["relevance"] == "POSSIBLY_RELEVANT":
                    best = r
            if best:
                matches.append({"stage": s["stage"], "label": s["label"], **best})
        out.append({**life.event_out(e), "matches": matches, "relevant": any(x["relevance"] == "RELEVANT" for x in matches)})
    return {"events": out, "note": "Relevance matching (place + period) only — Phase 6 decides exposure and impact."}


class ContextIn(In):
    topic: Literal["family-expectations", "marriage-norms", "education-expectations", "migration-attitudes", "gender-roles", "multi-generational-households", "social-status", "other"]
    country: Country3
    region: str | None = None
    yearStart: Year
    yearEnd: Year
    populationScope: str = Field(min_length=3)
    claim: str = Field(min_length=10)
    source: str = Field(min_length=3)
    sourceUrl: str = ""
    evidenceType: Literal["QUALITATIVE", "SURVEY_FINDING", "ETHNOGRAPHIC", "LEGAL_TEXT", "MEASURABLE_CLAIM"]
    confidence: Conf = "LOW"
    notes: str = ""


@router.get("/life/context")
def list_context(db: DB):
    return [life.context_out(c) for c in db.scalars(select(m.ContextEvidence).order_by(m.ContextEvidence.country, m.ContextEvidence.year_start))]


@router.post("/life/context", status_code=201)
def create_context(db: DB, r: ContextIn):
    if r.yearEnd < r.yearStart:
        raise HTTPException(422, "yearEnd must be >= yearStart")
    ts = repo.now_iso()
    c = m.ContextEvidence(id="CTX-" + uuid.uuid4().hex[:8], topic=r.topic, country=r.country.upper(), region=r.region, year_start=r.yearStart, year_end=r.yearEnd,
                          population_scope=r.populationScope, claim=r.claim, source=r.source, source_url=r.sourceUrl, evidence_type=r.evidenceType,
                          confidence=r.confidence, notes=r.notes, created_at=ts, updated_at=ts)
    db.add(c)
    db.commit()
    return life.context_out(c)


@router.delete("/life/context/{cid}", status_code=204)
def delete_context(cid: IdPath, db: DB):
    c = db.get(m.ContextEvidence, cid)
    if c is None:
        raise HTTPException(404, "Context record not found")
    db.delete(c)
    db.commit()


# ------------------------------------------------------------ episode evidence
@router.get("/episodes/{eid}/life/plan")
def plan(eid: IdPath, db: DB):
    _ep(db, eid)
    return life.plan_out(life.stage_plan(db, eid))


@router.get("/episodes/{eid}/life/matrix")
def matrix(eid: IdPath, db: DB):
    _ep(db, eid)
    return life.life_matrix(db, eid)


@router.get("/episodes/{eid}/life/matrix/{stage}/{domain}")
def cell(eid: IdPath, stage: IdPath, domain: IdPath, db: DB):
    _ep(db, eid)
    mx = life.life_matrix(db, eid, with_detail=True)
    for s in mx["stages"]:
        if s["stage"] == stage:
            for c in s["cells"]:
                if c["domain"] == domain:
                    return {"stage": {k: v for k, v in s.items() if k != "cells"}, "cell": c}
    raise HTTPException(404, "Cell not found")


@router.get("/episodes/{eid}/life/readiness")
def readiness(eid: IdPath, db: DB):
    _ep(db, eid)
    return life.readiness_v2(db, eid, _required(db))


@router.post("/episodes/{eid}/life/gaps/detect")
def detect(eid: IdPath, db: DB):
    _ep(db, eid)
    return [labor.gap_out(g) for g in life.detect_life_gaps(db, eid, _required(db))]


@router.get("/episodes/{eid}/life/migration-paths")
def paths(eid: IdPath, db: DB):
    _ep(db, eid)
    return life.migration_paths(db, eid)


class PathIn(In):
    origin: Country3
    destination: Country3
    yearStart: Year
    yearEnd: Year
    notes: str = ""


@router.post("/episodes/{eid}/life/migration-paths", status_code=201)
def add_path(eid: IdPath, db: DB, r: PathIn):
    _ep(db, eid)
    db.add(m.MigrationPath(id="MP-" + uuid.uuid4().hex[:8], episode_id=eid, origin=r.origin.upper(), destination=r.destination.upper(), year_start=r.yearStart,
                           year_end=r.yearEnd, notes=r.notes, created_at=repo.now_iso()))
    db.commit()
    return life.migration_paths(db, eid)


# ------------------------------------------------------------ assumptions
class AssumptionIn(In):
    domain: str = Field(min_length=2, max_length=40)
    lifeStage: str = Field(min_length=2, max_length=40)
    claim: str = Field(min_length=5)
    value: str = ""
    unit: str = ""
    yearStart: Year | None = None
    yearEnd: Year | None = None
    reason: str = Field(min_length=20)
    supportingEvidence: list[str] = []
    confidence: Conf = "LOW"


@router.get("/episodes/{eid}/assumptions")
def list_assumptions(eid: IdPath, db: DB):
    _ep(db, eid)
    return life.assumption_register(db, eid)


@router.post("/episodes/{eid}/assumptions", status_code=201)
def create_assumption(eid: IdPath, db: DB, r: AssumptionIn):
    _ep(db, eid)
    if r.lifeStage not in life.STAGE_LABEL:
        raise HTTPException(422, "Unknown life stage")
    ts = repo.now_iso()
    a = m.Assumption(id="ASM-" + uuid.uuid4().hex[:8], episode_id=eid, domain=r.domain, life_stage=r.lifeStage, claim=r.claim, value=r.value, unit=r.unit,
                     year_start=r.yearStart, year_end=r.yearEnd, reason=r.reason, created_by="user", supporting_evidence=r.supportingEvidence,
                     confidence=r.confidence, status="active", created_at=ts, updated_at=ts)
    db.add(a)
    db.commit()
    return life.assumption_out(a)


@router.post("/assumptions/{aid}/retire")
def retire_assumption(aid: IdPath, db: DB):
    a = db.get(m.Assumption, aid)
    if a is None:
        raise HTTPException(404, "Assumption not found")
    a.status, a.updated_at = "retired", repo.now_iso()
    db.commit()
    return life.assumption_out(a)


# ------------------------------------------------------------ life-stage baselines
class LifeBaselineIn(In):
    domain: str
    lifeStage: str
    yearStart: Year
    yearEnd: Year
    lifeObservationIds: list[str] = []
    assumptionIds: list[str] = []
    estimateKind: Literal["POINT", "RANGE", "DISTRIBUTION"] | None = None
    low: str | None = None
    high: str | None = None
    point: str | None = None
    distribution: list[dict] | None = None
    unit: str | None = None
    metric: str | None = None
    scope: str | None = None
    reasoning: str = ""


@router.get("/episodes/{eid}/life/baselines")
def list_lb(eid: IdPath, db: DB):
    _ep(db, eid)
    return [life.life_baseline_out(b) for b in db.scalars(select(m.LifeStageBaseline).where(m.LifeStageBaseline.episode_id == eid).order_by(m.LifeStageBaseline.created_at))]


@router.post("/episodes/{eid}/life/baselines", status_code=201)
def create_lb(eid: IdPath, db: DB, r: LifeBaselineIn):
    _ep(db, eid)
    try:
        b = life.create_life_baseline(db, eid, r.model_dump())
    except life.LifeError as e:
        raise HTTPException(422, str(e)) from e
    return life.life_baseline_out(b)


@router.post("/life/baselines/{bid}/approve")
def approve_lb(bid: IdPath, db: DB, approved: bool = True):
    b = db.get(m.LifeStageBaseline, bid)
    if b is None:
        raise HTTPException(404, "Baseline not found")
    b.user_approved, b.approved_at, b.updated_at = approved, (repo.now_iso() if approved else None), repo.now_iso()
    db.commit()
    return life.life_baseline_out(b)


@router.delete("/life/baselines/{bid}", status_code=204)
def delete_lb(bid: IdPath, db: DB):
    b = db.get(m.LifeStageBaseline, bid)
    if b is None:
        raise HTTPException(404, "Baseline not found")
    db.delete(b)
    db.commit()
