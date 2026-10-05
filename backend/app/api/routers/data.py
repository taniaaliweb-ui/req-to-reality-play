"""Truth + economic engine endpoints. React only ever sees these — never a provider directly."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import providers
from app.db import models as m
from app.db.database import get_db
from app.providers.base import ProviderError
from app.services import economic_engine as eng
from app.services import repository as repo
from app.services import truth

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]
IdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:\-]{1,160}$")]
Country = Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}$")]
Year = Annotated[int, Field(ge=1960, le=2100)]
Cur = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class In(BaseModel):
    model_config = {"populate_by_name": True, "extra": "forbid"}


class SyncReq(In):
    indicators: list[str] = Field(min_length=1, max_length=10)
    countries: list[Country] = Field(min_length=1, max_length=20)
    yearStart: Year
    yearEnd: Year


class ManualObs(In):
    indicatorCode: str = Field(min_length=1, max_length=80)
    indicatorName: str = ""
    countryCode: Country
    countryName: str = ""
    year: Year
    value: str = Field(max_length=60)
    unit: str = Field(min_length=1, max_length=120)
    dataset: str = Field(min_length=1, max_length=200)
    sourceOrganization: str = Field(min_length=1, max_length=300)
    sourceNote: str = ""
    sourceUrl: str = ""


class ToFactsReq(In):
    observationIds: list[str] = Field(min_length=1, max_length=500)


class InflationReq(In):
    episodeId: str | None = None
    country: Country
    amount: str = Field(max_length=40)
    sourceYear: Year
    targetYear: Year
    currency: Cur | None = None
    save: bool = False


class FxReq(In):
    episodeId: str | None = None
    amount: str = Field(max_length=40)
    year: Year
    fromCountry: Country
    toCountry: Country
    fromCurrency: Cur | None = None
    toCurrency: Cur | None = None
    save: bool = False


class SnapshotReq(In):
    label: str = Field(min_length=1, max_length=200)


def _settings(db: Session) -> dict:
    return repo.get_settings(db)


@router.get("/data/providers")
def list_providers(db: DB, check: bool = False):
    st = _settings(db)
    wb = providers.get_world_bank()
    last = db.scalar(select(m.ProviderSync).where(m.ProviderSync.provider == "world-bank").order_by(m.ProviderSync.started_at.desc()))
    n_obs = db.scalar(select(func.count()).select_from(m.ExternalObservation).where(m.ExternalObservation.provider == "world-bank")) or 0
    enabled = st["externalDataEnabled"] and st["worldBankEnabled"]
    if not enabled:
        status, detail = "disabled", "Disabled in Settings."
    elif check:
        ok, kind = wb.ping()
        status, detail = ("available", "API reachable") if ok else ("offline" if kind in ("network", "timeout") else "error", kind)
    else:
        status, detail = (("error" if last.status == "error" else "available"), last.summary.get("error", "")) if last else ("unknown", "Not checked")
    return [
        {**wb.describe(), "status": status, "detail": detail, "enabled": enabled, "storedObservations": n_obs,
         "lastSync": {"at": last.finished_at, "status": last.status, "summary": last.summary} if last else None},
        {**providers.manual_provider.describe(), "status": "available", "detail": "Values entered with a named source.", "enabled": True,
         "storedObservations": db.scalar(select(func.count()).select_from(m.ExternalObservation).where(m.ExternalObservation.provider == "manual")) or 0, "lastSync": None},
    ]


@router.post("/data/world-bank/sync")
def sync_world_bank(db: DB, req: SyncReq):
    st = _settings(db)
    if not (st["externalDataEnabled"] and st["worldBankEnabled"]):
        raise HTTPException(403, "External data access is disabled in Settings.")
    if req.yearEnd < req.yearStart:
        raise HTTPException(422, "yearEnd must be >= yearStart")
    wb = providers.get_world_bank()
    started = repo.now_iso()
    per: list[dict] = []
    status = "ok"
    error = None
    for ind in req.indicators:
        try:
            res = wb.fetch_series(ind, [c.upper() for c in req.countries], req.yearStart, req.yearEnd)
        except ProviderError as e:
            status, error = "error", f"{e.kind}: {e}"
            per.append({"indicator": ind, "error": str(e), "kind": e.kind, "retrieved": 0, "unavailable": None})
            break
        counts = truth.store_observations(db, res.observations)
        if res.missing or res.countries_unknown:
            status = "partial" if status == "ok" else status
        per.append({"indicator": ind, "retrieved": len(res.observations), "unavailable": len(res.missing), "missing": res.missing[:200],
                    "unknownCountries": res.countries_unknown, **counts})
    summary = {"indicators": per, "retrieved": sum(p["retrieved"] for p in per), "unavailable": sum(p["unavailable"] or 0 for p in per)}
    if error:
        summary["error"] = error
    db.add(m.ProviderSync(id="SYNC-" + uuid.uuid4().hex[:10], provider="world-bank", started_at=started, finished_at=repo.now_iso(),
                          status=status, request=req.model_dump(), summary=summary))
    db.commit()
    return {"provider": "world-bank", "status": status, "startedAt": started, "finishedAt": repo.now_iso(), **summary}


@router.post("/data/manual/observations", status_code=201)
def add_manual(db: DB, obs: ManualObs):
    try:
        o = providers.manual_provider.normalize(obs.model_dump())
    except ProviderError as e:
        raise HTTPException(422, str(e)) from None
    counts = truth.store_observations(db, [o])
    db.commit()
    row = db.get(m.ExternalObservation, truth.obs_id("manual", o.indicator_code, o.country_code, o.year))
    return {**truth.obs_out(row), **counts}


@router.get("/data/observations")
def list_observations(db: DB, country: str | None = None, indicator: str | None = None, provider: str | None = None,
                      yearStart: int | None = None, yearEnd: int | None = None, limit: Annotated[int, Query(ge=1, le=5000)] = 2000):
    q = select(m.ExternalObservation)
    if country:
        q = q.where(m.ExternalObservation.country_code == country.upper())
    if indicator:
        q = q.where(m.ExternalObservation.indicator_code == indicator)
    if provider:
        q = q.where(m.ExternalObservation.provider == provider)
    if yearStart is not None:
        q = q.where(m.ExternalObservation.year >= yearStart)
    if yearEnd is not None:
        q = q.where(m.ExternalObservation.year <= yearEnd)
    rows = list(db.scalars(q.order_by(m.ExternalObservation.indicator_code, m.ExternalObservation.country_code, m.ExternalObservation.year).limit(limit)))
    rev = dict(db.execute(select(m.ObservationRevision.observation_id, func.count()).group_by(m.ObservationRevision.observation_id)).all())
    return [{**truth.obs_out(r), "revisions": rev.get(r.id, 0)} for r in rows]


@router.get("/data/observations/{oid}/revisions")
def observation_revisions(oid: IdPath, db: DB):
    return [{"oldValue": r.old_value, "newValue": r.new_value, "oldRetrievedAt": r.old_retrieved_at, "newRetrievedAt": r.new_retrieved_at}
            for r in db.scalars(select(m.ObservationRevision).where(m.ObservationRevision.observation_id == oid).order_by(m.ObservationRevision.id))]


@router.post("/episodes/{eid}/facts/from-observations")
def facts_from_observations(eid: IdPath, db: DB, req: ToFactsReq):
    if db.get(m.Episode, eid) is None:
        raise HTTPException(404, "Episode not found")
    created, missing = [], []
    for oid in req.observationIds:
        o = db.get(m.ExternalObservation, oid)
        if o is None:
            missing.append(oid)
            continue
        created.append(truth.fact_for_observation(db, eid, o).id)
    db.commit()
    return {"factIds": created, "missingObservations": missing}


@router.post("/economics/inflation-adjust")
def inflation_adjust(db: DB, req: InflationReq):
    if req.sourceYear == req.targetYear:
        pass  # allowed: identity, factor 1
    return truth.inflation_adjust(db, episode_id=req.episodeId, country=req.country, amount=req.amount, source_year=req.sourceYear,
                                  target_year=req.targetYear, currency=req.currency, save=req.save)


@router.post("/economics/currency-convert")
def currency_convert(db: DB, req: FxReq):
    return truth.currency_convert(db, episode_id=req.episodeId, amount=req.amount, year=req.year, from_country=req.fromCountry,
                                  to_country=req.toCountry, from_currency=req.fromCurrency, to_currency=req.toCurrency, save=req.save)


@router.get("/facts/{fid}/lineage")
def fact_lineage(fid: IdPath, db: DB):
    out = truth.lineage(db, fid)
    if out is None:
        raise HTTPException(404, "Fact not found")
    return out


@router.get("/episodes/{eid}/economics/verified")
def verified_economics(eid: IdPath, db: DB, baseYear: Annotated[int, Query(ge=1960, le=2100)] = 2010):
    if db.get(m.Episode, eid) is None:
        raise HTTPException(404, "Episode not found")
    return truth.verified_economics(db, eid, baseYear)


@router.post("/episodes/{eid}/dataset-snapshots", status_code=201)
def pin_snapshot(eid: IdPath, db: DB, req: SnapshotReq):
    if db.get(m.Episode, eid) is None:
        raise HTTPException(404, "Episode not found")
    return truth.pin_snapshot(db, eid, req.label)


@router.get("/episodes/{eid}/dataset-snapshots")
def list_snapshots(eid: IdPath, db: DB):
    return [{"id": s.id, "label": s.label, "createdAt": s.created_at, "items": s.items}
            for s in db.scalars(select(m.EpisodeDatasetSnapshot).where(m.EpisodeDatasetSnapshot.episode_id == eid))]


@router.get("/engine")
def engine_info():
    return {"truthEngine": "online", "economicEngine": "online", "engineVersion": eng.ENGINE_VERSION,
            "formulas": [eng.INFLATION_FORMULA, eng.FX_FORMULA], "rounding": "Decimal, 28 significant digits; stored unrounded; display ROUND_HALF_EVEN to 2 dp"}
