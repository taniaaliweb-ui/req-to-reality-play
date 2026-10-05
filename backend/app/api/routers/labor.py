"""Phase 4 endpoints: labour providers, wage evidence, profiles, matching, baselines, gaps,
readiness, households and immutable dataset snapshots. React reaches these only via lifespanApi.ts."""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import providers
from app.db import models as m
from app.db.database import get_db
from app.providers.base import ProviderError
from app.services import economic_engine as eng
from app.services import labor
from app.services import repository as repo
from app.services import snapshots as snaps
from app.services import truth

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
IdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:\-]{1,200}$")]
Country3 = Annotated[str, Field(pattern=r"^[A-Za-z]{3}$")]
Year = Annotated[int, Field(ge=1800, le=2100)]
Stage = Literal["birth-family", "education", "first-employment", "migration-wage", "housing", "retirement"]


class In(BaseModel):
    model_config = {"populate_by_name": True, "extra": "forbid"}


def _ep(db: Session, eid: str) -> m.Episode:
    ep = db.get(m.Episode, eid)
    if ep is None:
        raise HTTPException(404, "Episode not found")
    return ep


# ------------------------------------------------------------ ILOSTAT
class IloSync(In):
    indicators: list[str] = Field(min_length=1, max_length=10)
    countries: list[Country3] = Field(min_length=1, max_length=20)
    yearStart: Year
    yearEnd: Year


@router.post("/data/ilostat/sync")
def sync_ilostat(db: DB, req: IloSync):
    st = repo.get_settings(db)
    if not (st["externalDataEnabled"] and st.get("ilostatEnabled", True)):
        raise HTTPException(403, "ILOSTAT access is disabled in Settings.")
    if req.yearEnd < req.yearStart:
        raise HTTPException(422, "yearEnd must be >= yearStart")
    p = providers.get_ilostat()
    started = repo.now_iso()
    per, status, error = [], "ok", None
    for ind in req.indicators:
        try:
            res = p.fetch_series(ind, req.countries, req.yearStart, req.yearEnd)
        except ProviderError as e:
            status, error = ("error" if not per else "partial"), f"{e.kind}: {e}"
            per.append({"indicator": ind, "error": str(e), "kind": e.kind, "retrieved": 0, "unavailable": None})
            if e.kind in ("network", "timeout", "rate-limit"):
                break
            continue
        counts = truth.store_observations(db, res.observations)
        db.flush()
        wages = 0
        for o in res.observations:
            row = db.get(m.ExternalObservation, o.obs_key)
            if row is not None and labor.upsert_wage_from_ilo(db, row) is not None:
                wages += 1
        missing_years = sorted({(x["country"], x["year"]) for x in res.missing if x["reason"] == "no observation published"})
        if missing_years:
            status = "partial" if status == "ok" else status
        per.append({"indicator": ind, "retrieved": len(res.observations), "unavailable": len(missing_years), "wageObservations": wages,
                    "missing": [{"country": c, "year": y, "reason": "no observation published"} for c, y in missing_years][:200],
                    "skippedSubAnnual": getattr(res, "skipped_subannual", 0), "unknownCountries": res.countries_unknown, **counts})
    summary = {"indicators": per, "retrieved": sum(x["retrieved"] for x in per), "unavailable": sum(x["unavailable"] or 0 for x in per)}
    if error:
        summary["error"] = error
    db.add(m.ProviderSync(id="SYNC-" + uuid.uuid4().hex[:10], provider="ilostat", started_at=started, finished_at=repo.now_iso(), status=status,
                          request=req.model_dump(), summary=summary))
    db.commit()
    return {"provider": "ilostat", "status": status, "startedAt": started, "finishedAt": repo.now_iso(), **summary}


@router.get("/labor/wage-observations")
def wage_observations(db: DB, country: str | None = None, provider: str | None = None, yearStart: int | None = None, yearEnd: int | None = None,
                      occupation: str | None = None, education: str | None = None, sex: str | None = None, urbanRural: str | None = None,
                      industry: str | None = None, citizenship: str | None = None, statistic: str | None = None,
                      limit: Annotated[int, Query(ge=1, le=5000)] = 2000):
    q = select(m.WageObservation)
    W = m.WageObservation
    for col, v in ((W.country, country and country.upper()), (W.provider, provider), (W.sex, sex and sex.upper()), (W.rural_urban, urbanRural and urbanRural.upper()),
                   (W.citizenship, citizenship and citizenship.upper()), (W.statistic_type, statistic and statistic.upper())):
        if v:
            q = q.where(col == v)
    if yearStart is not None:
        q = q.where(W.year >= yearStart)
    if yearEnd is not None:
        q = q.where(W.year <= yearEnd)
    if occupation:
        q = q.where((W.occupation_code == occupation) | W.occupation_label.ilike(f"%{occupation}%"))
    if education:
        q = q.where((W.education_code == education) | W.education_label.ilike(f"%{education}%"))
    if industry:
        q = q.where((W.industry_code == industry) | W.industry_label.ilike(f"%{industry}%"))
    rows = list(db.scalars(q.order_by(W.country, W.external_observation_id).limit(limit)))
    ret = {o.id: o.retrieved_at for o in db.scalars(select(m.ExternalObservation).where(m.ExternalObservation.id.in_([r.external_observation_id for r in rows])))}
    return [{**labor.wage_out(r), "retrievedAt": ret.get(r.external_observation_id)} for r in rows]


@router.get("/labor/distributions")
def distributions(db: DB, country: str | None = None):
    q = select(m.WageDistribution)
    if country:
        q = q.where(m.WageDistribution.country == country.upper())
    return [labor.dist_out(db, d) for d in db.scalars(q.order_by(m.WageDistribution.country, m.WageDistribution.year))]


class ImportReq(In):
    provider: Literal["manual", "india-mospi", "uae-fcsc"]
    csv: str = Field(min_length=1, max_length=5_000_000)


@router.post("/labor/import/preview")
def import_preview(db: DB, req: ImportReq):
    out = labor.parse_import(db, req.provider, req.csv)
    out["rows"] = out["rows"][:500]
    return out


@router.post("/labor/import/commit")
def import_commit(db: DB, req: ImportReq):
    return labor.commit_import(db, req.provider, providers.IMPORT_PROVIDERS[req.provider].provider_name, req.csv)


@router.get("/labor/import/template")
def import_template():
    return {"header": labor.TEMPLATE_HEADER, "required": list(labor.REQUIRED),
            "example": "metric,value,unit,currency,country,year,source,source_organization,pay_period,statistic_type,gross_or_net,occupation,sex,urban_rural\n"
                       "Median monthly earnings of regular wage employees,12000,INR per month,INR,IND,2019,PLFS Annual Report 2018-19 Table X,"
                       "Ministry of Statistics and Programme Implementation,MONTHLY,MEDIAN,UNKNOWN,,TOTAL,URBAN"}


# ------------------------------------------------------------ profiles + matching
class ProfileIn(In):
    lifeStage: Stage
    targetYear: Year
    yearStart: Year
    yearEnd: Year
    country: Country3
    region: str = ""
    urbanRural: Literal["", "URBAN", "RURAL"] = ""
    educationLevel: Literal["", "LTB", "BAS", "INT", "ADV"] = ""
    occupation: str = ""
    occupationCode: str = Field("", max_length=10)
    occupationClassification: Literal["ISCO-08", "ISCO-88"] = "ISCO-08"
    industry: str = ""
    industryCode: str = ""
    employmentStatus: Literal["", "EMPLOYEE", "SELF_EMPLOYED", "EMPLOYER", "UNPAID", "UNKNOWN"] = ""
    formalInformal: Literal["", "FORMAL", "INFORMAL"] = ""
    yearsExperience: int | None = Field(None, ge=0, le=80)
    age: int | None = Field(None, ge=0, le=120)
    sex: Literal["", "MALE", "FEMALE"] = ""
    citizenship: Literal["", "NATIONAL", "NON_NATIONAL"] = ""
    migrantStatus: str = ""
    employmentSector: str = ""
    notes: str = ""


def _profile_fields(p: ProfileIn) -> dict:
    d = p.model_dump()
    return {k: (d[k].upper() if k == "country" else d[k]) for k in labor.PROFILE_KEYS}


@router.get("/episodes/{eid}/economic-profiles")
def list_profiles(eid: IdPath, db: DB):
    return [labor.profile_out(p) for p in db.scalars(select(m.CharacterEconomicProfile).where(m.CharacterEconomicProfile.episode_id == eid)
                                                     .order_by(m.CharacterEconomicProfile.year_start))]


@router.post("/episodes/{eid}/economic-profiles", status_code=201)
def create_profile(eid: IdPath, db: DB, p: ProfileIn):
    _ep(db, eid)
    if p.yearEnd < p.yearStart:
        raise HTTPException(422, "yearEnd must be >= yearStart")
    ts = repo.now_iso()
    row = m.CharacterEconomicProfile(id="PRF-" + uuid.uuid4().hex[:8], episode_id=eid, life_stage=p.lifeStage, target_year=p.targetYear,
                                     year_start=p.yearStart, year_end=p.yearEnd, fields=_profile_fields(p), created_at=ts, updated_at=ts)
    db.add(row)
    db.commit()
    return labor.profile_out(row)


@router.put("/economic-profiles/{pid}")
def update_profile(pid: IdPath, db: DB, p: ProfileIn):
    row = db.get(m.CharacterEconomicProfile, pid)
    if row is None:
        raise HTTPException(404, "Profile not found")
    row.life_stage, row.target_year, row.year_start, row.year_end = p.lifeStage, p.targetYear, p.yearStart, p.yearEnd
    row.fields = _profile_fields(p)
    row.updated_at = repo.now_iso()
    db.commit()
    return labor.profile_out(row)


@router.delete("/economic-profiles/{pid}", status_code=204)
def delete_profile(pid: IdPath, db: DB):
    row = db.get(m.CharacterEconomicProfile, pid)
    if row is None:
        raise HTTPException(404, "Profile not found")
    db.delete(row)
    db.commit()


@router.get("/economic-profiles/{pid}/candidates")
def profile_candidates(pid: IdPath, db: DB, limit: Annotated[int, Query(ge=1, le=200)] = 25):
    row = db.get(m.CharacterEconomicProfile, pid)
    if row is None:
        raise HTTPException(404, "Profile not found")
    return labor.candidates(db, row, limit)


class ReviewIn(In):
    wageObservationId: str
    decision: Literal["rejected", "flagged", "clear"]
    note: str = ""


@router.post("/economic-profiles/{pid}/reviews")
def review_candidate(pid: IdPath, db: DB, r: ReviewIn):
    if db.get(m.CharacterEconomicProfile, pid) is None:
        raise HTTPException(404, "Profile not found")
    row = db.get(m.CandidateReview, (pid, r.wageObservationId))
    if r.decision == "clear":
        if row:
            db.delete(row)
    elif row is None:
        db.add(m.CandidateReview(profile_id=pid, wage_observation_id=r.wageObservationId, decision=r.decision, note=r.note, created_at=repo.now_iso()))
    else:
        row.decision, row.note = r.decision, r.note
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------ baselines
class Annualization(In):
    assumptions: dict[str, str | int | float]


class BaselineIn(In):
    profileId: str | None = None
    lifeStage: Stage
    yearStart: Year
    yearEnd: Year
    baselineType: Literal["FACT_SUPPORTED", "ASSUMPTION", "DERIVED"]
    wageObservationIds: list[str] = Field(default_factory=list, max_length=50)
    evidenceFactIds: list[str] = Field(default_factory=list, max_length=50)
    adjustToYear: Year | None = None
    low: str | None = None
    high: str | None = None
    point: str | None = None
    currency: str | None = None
    payPeriod: Literal["HOURLY", "DAILY", "WEEKLY", "MONTHLY", "ANNUAL"] | None = None
    grossOrNet: Literal["GROSS", "NET", "UNKNOWN"] | None = None
    reasoning: str = ""
    occupation: str = ""
    employmentType: str = ""
    annualization: Annualization | None = None


@router.get("/episodes/{eid}/baselines")
def list_baselines(eid: IdPath, db: DB):
    return [labor.baseline_out(db, b) for b in db.scalars(select(m.EconomicBaseline).where(m.EconomicBaseline.episode_id == eid).order_by(m.EconomicBaseline.year_start))]


@router.post("/episodes/{eid}/baselines", status_code=201)
def create_baseline(eid: IdPath, db: DB, req: BaselineIn):
    _ep(db, eid)
    try:
        b = labor.create_baseline(db, eid, req.model_dump(exclude_none=False) | {"annualization": req.annualization.model_dump() if req.annualization else None})
    except labor.BaselineError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from None
    return labor.baseline_out(db, b)


@router.post("/baselines/{bid}/approve")
def approve_baseline(bid: IdPath, db: DB, approved: bool = True):
    b = db.get(m.EconomicBaseline, bid)
    if b is None:
        raise HTTPException(404, "Baseline not found")
    if approved and b.confidence == "INSUFFICIENT_DATA" and b.baseline_type != "ASSUMPTION":
        raise HTTPException(422, "Insufficient evidence — record an explicit ASSUMPTION instead")
    b.user_approved, b.approved_at, b.updated_at = approved, repo.now_iso() if approved else None, repo.now_iso()
    db.commit()
    return labor.baseline_out(db, b)


@router.delete("/baselines/{bid}", status_code=204)
def delete_baseline(bid: IdPath, db: DB):
    b = db.get(m.EconomicBaseline, bid)
    if b is None:
        raise HTTPException(404, "Baseline not found")
    db.delete(b)
    db.commit()


class AnnualizeIn(In):
    amount: str = Field(max_length=40)
    payPeriod: Literal["HOURLY", "DAILY", "WEEKLY", "MONTHLY", "ANNUAL"]
    assumptions: dict[str, str | int | float] = Field(default_factory=dict)


@router.post("/economics/annualize")
def annualize(req: AnnualizeIn):
    return eng.annualize_wage(req.amount, req.payPeriod, req.assumptions).as_dict()


# ------------------------------------------------------------ gaps + readiness
@router.get("/episodes/{eid}/evidence-gaps")
def list_gaps(eid: IdPath, db: DB):
    return [labor.gap_out(g) for g in db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == eid).order_by(m.EvidenceGap.created_at))]


@router.post("/episodes/{eid}/evidence-gaps/detect")
def detect(eid: IdPath, db: DB):
    _ep(db, eid)
    return [labor.gap_out(g) for g in labor.detect_gaps(db, eid)]


class GapIn(In):
    title: str = Field(min_length=3, max_length=300)
    reason: str = ""
    category: Literal["Employment", "Migration", "Education", "Housing", "Economy"]
    country: str = ""
    yearStart: Year
    yearEnd: Year
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"


@router.post("/episodes/{eid}/evidence-gaps", status_code=201)
def add_gap(eid: IdPath, db: DB, g: GapIn):
    _ep(db, eid)
    row = m.EvidenceGap(id="GAP-" + uuid.uuid4().hex[:8], episode_id=eid, gap_key="manual:" + uuid.uuid4().hex[:8], title=g.title, reason=g.reason, category=g.category,
                        country=g.country, year_start=g.yearStart, year_end=g.yearEnd, priority=g.priority, status="open", auto=False, created_at=repo.now_iso())
    db.add(row)
    db.commit()
    return labor.gap_out(row)


@router.post("/evidence-gaps/{gid}/research-task", status_code=201)
def gap_task(gid: IdPath, db: DB):
    g = db.get(m.EvidenceGap, gid)
    if g is None:
        raise HTTPException(404, "Gap not found")
    t = labor.task_from_gap(db, g)
    return {"taskId": t.id, "gap": labor.gap_out(g)}


@router.get("/episodes/{eid}/readiness")
def get_readiness(eid: IdPath, db: DB):
    _ep(db, eid)
    return labor.readiness(db, eid)


# ------------------------------------------------------------ households (structure only)
class MemberIn(In):
    role: Literal["self", "spouse", "parent", "child", "sibling", "other"]
    name: str = ""
    employmentKind: Literal["not-employed", "employee", "self-employed", "unknown"] = "unknown"


class HouseholdIn(In):
    label: str = Field(min_length=1, max_length=200)
    yearStart: Year
    yearEnd: Year
    members: list[MemberIn] = Field(default_factory=list, max_length=20)


class StreamIn(In):
    memberId: str | None = None
    kind: Literal["employment", "self-employment", "remittance-sent", "remittance-received", "pension", "investment", "other"]
    yearStart: Year
    yearEnd: Year
    low: str | None = None
    high: str | None = None
    currency: str | None = None
    payPeriod: Literal["HOURLY", "DAILY", "WEEKLY", "MONTHLY", "ANNUAL"] | None = None
    basis: Literal["FACT_SUPPORTED", "ASSUMPTION", "DERIVED", "UNKNOWN"] = "UNKNOWN"
    baselineId: str | None = None
    factId: str | None = None
    notes: str = ""


def _hh_out(db: Session, h: m.HouseholdUnit) -> dict:
    streams = list(db.scalars(select(m.IncomeStream).where(m.IncomeStream.household_id == h.id)))
    return {"id": h.id, "episodeId": h.episode_id, "label": h.label, "yearStart": h.year_start, "yearEnd": h.year_end, "members": h.members,
            "streams": [{"id": s.id, "memberId": s.member_id, "kind": s.kind, "yearStart": s.year_start, "yearEnd": s.year_end, "low": s.low, "high": s.high,
                         "currency": s.currency, "payPeriod": s.pay_period, "basis": s.basis, "baselineId": s.baseline_id, "factId": s.fact_id, "notes": s.notes}
                        for s in streams]}


@router.get("/episodes/{eid}/households")
def list_households(eid: IdPath, db: DB):
    return [_hh_out(db, h) for h in db.scalars(select(m.HouseholdUnit).where(m.HouseholdUnit.episode_id == eid).order_by(m.HouseholdUnit.year_start))]


@router.post("/episodes/{eid}/households", status_code=201)
def create_household(eid: IdPath, db: DB, h: HouseholdIn):
    _ep(db, eid)
    row = m.HouseholdUnit(id="HH-" + uuid.uuid4().hex[:8], episode_id=eid, label=h.label, year_start=h.yearStart, year_end=h.yearEnd,
                          members=[{"id": "MB-" + uuid.uuid4().hex[:6], **mm.model_dump()} for mm in h.members], created_at=repo.now_iso())
    db.add(row)
    db.commit()
    return _hh_out(db, row)


@router.post("/households/{hid}/streams", status_code=201)
def add_stream(hid: IdPath, db: DB, s: StreamIn):
    h = db.get(m.HouseholdUnit, hid)
    if h is None:
        raise HTTPException(404, "Household not found")
    has_amount = s.low not in (None, "") or s.high not in (None, "")
    if has_amount:
        if s.basis == "UNKNOWN":
            raise HTTPException(422, "An amount needs a basis (fact-supported, derived or explicit assumption)")
        if s.basis in ("FACT_SUPPORTED", "DERIVED") and not (s.baselineId and db.get(m.EconomicBaseline, s.baselineId)) and not (s.factId and db.get(m.Fact, s.factId)):
            raise HTTPException(422, "Fact-supported or derived amounts must reference a baseline or fact")
        if s.basis == "ASSUMPTION" and len(s.notes.strip()) < 20:
            raise HTTPException(422, "Assumed amounts need written reasoning in notes (at least 20 characters)")
        if not s.currency:
            raise HTTPException(422, "currency is required for an amount")
    if s.memberId and s.memberId not in {mm["id"] for mm in h.members}:
        raise HTTPException(422, "Unknown household member")
    db.add(m.IncomeStream(id="INC-" + uuid.uuid4().hex[:8], household_id=hid, member_id=s.memberId, kind=s.kind, year_start=s.yearStart, year_end=s.yearEnd,
                          low=s.low or None, high=s.high or None, currency=s.currency, pay_period=s.payPeriod, basis=s.basis, baseline_id=s.baselineId,
                          fact_id=s.factId, notes=s.notes, created_at=repo.now_iso()))
    db.commit()
    return _hh_out(db, h)


@router.delete("/income-streams/{sid}", status_code=204)
def delete_stream(sid: IdPath, db: DB):
    s = db.get(m.IncomeStream, sid)
    if s is None:
        raise HTTPException(404, "Income stream not found")
    db.delete(s)
    db.commit()


@router.delete("/households/{hid}", status_code=204)
def delete_household(hid: IdPath, db: DB):
    h = db.get(m.HouseholdUnit, hid)
    if h is None:
        raise HTTPException(404, "Household not found")
    db.delete(h)
    db.commit()


# ------------------------------------------------------------ dataset snapshots
class SnapIn(In):
    name: str = Field(min_length=1, max_length=180)
    notes: str = ""


def _snap(db: Session, sid: str) -> m.EpisodeDatasetSnapshot:
    s = db.get(m.EpisodeDatasetSnapshot, sid)
    if s is None:
        raise HTTPException(404, "Snapshot not found")
    return s


def _guard(fn):
    try:
        return fn()
    except snaps.SnapshotError as e:
        db_err = HTTPException(e.status, str(e))
        raise db_err from None


@router.get("/episodes/{eid}/snapshots")
def list_snaps(eid: IdPath, db: DB):
    return snaps.list_for(db, eid)


@router.post("/episodes/{eid}/snapshots", status_code=201)
def create_snap(eid: IdPath, db: DB, req: SnapIn):
    _ep(db, eid)
    return snaps.summary(db, snaps.create(db, eid, req.name, req.notes))


@router.get("/snapshots/diff")
def diff_snaps(db: DB, a: str, b: str):
    return snaps.diff(db, _snap(db, a), _snap(db, b))


@router.get("/snapshots/{sid}")
def get_snap(sid: IdPath, db: DB):
    return snaps.detail(db, _snap(db, sid))


@router.post("/snapshots/{sid}/refresh")
def refresh_snap(sid: IdPath, db: DB):
    s = _snap(db, sid)
    _guard(lambda: snaps.refresh(db, s))
    return snaps.summary(db, s)


@router.post("/snapshots/{sid}/finalize")
def finalize_snap(sid: IdPath, db: DB):
    s = _snap(db, sid)
    _guard(lambda: snaps.finalize(db, s))
    return snaps.summary(db, s)


@router.post("/snapshots/{sid}/new-version", status_code=201)
def new_version(sid: IdPath, db: DB):
    s = _snap(db, sid)
    return snaps.summary(db, snaps.create(db, s.episode_id, s.label, f"New version of {s.label}", parent=s))


@router.delete("/snapshots/{sid}", status_code=204)
def delete_snap(sid: IdPath, db: DB):
    s = _snap(db, sid)
    _guard(lambda: snaps.delete(db, s))
