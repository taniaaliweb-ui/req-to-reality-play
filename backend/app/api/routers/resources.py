"""Episodes, their owned resources, and the global source registry."""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.db.database import get_db
from app.domain.audit import run_audits
from app.domain.receipt import derive_receipt
from app.schemas import records as s
from app.services import repository as repo

router = APIRouter()
IdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:\-]{1,80}$")]
DB = Annotated[Session, Depends(get_db)]


def _episode(db: Session, eid: str) -> m.Episode:
    ep = db.get(m.Episode, eid)
    if ep is None:
        raise HTTPException(404, f"Episode {eid} not found")
    return ep


def _validate(schema: type[s.Schema], payload: dict) -> Any:
    try:
        return schema.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None


# ---------- Episodes ----------
@router.get("/episodes")
def list_episodes(db: DB):
    return [repo.episode_to_out(e) for e in db.scalars(select(m.Episode).order_by(m.Episode.created_at.desc()))]


@router.post("/episodes", status_code=201)
def create_episode(db: DB, payload: dict = Body(...)):
    payload.setdefault("id", str(uuid.uuid4()))
    obj = _validate(s.EpisodeIn, payload)
    if db.get(m.Episode, obj.id):
        raise HTTPException(409, "Episode already exists")
    ep = repo.upsert_episode(db, obj)
    db.commit()
    return repo.episode_to_out(ep)


@router.get("/episodes/{eid}")
def get_episode(eid: IdPath, db: DB):
    return repo.episode_to_out(_episode(db, eid))


@router.put("/episodes/{eid}")
def put_episode(eid: IdPath, db: DB, payload: dict = Body(...)):
    obj = _validate(s.EpisodeIn, {**payload, "id": eid})
    ep = repo.upsert_episode(db, obj)
    db.commit()
    return repo.episode_to_out(ep)


@router.patch("/episodes/{eid}")
def patch_episode(eid: IdPath, db: DB, payload: dict = Body(...)):
    current = repo.episode_to_out(_episode(db, eid))
    obj = _validate(s.EpisodeIn, {**current, **payload, "id": eid})
    ep = repo.upsert_episode(db, obj)
    db.commit()
    return repo.episode_to_out(ep)


@router.delete("/episodes/{eid}", status_code=204)
def delete_episode(eid: IdPath, db: DB):
    db.delete(_episode(db, eid))
    db.commit()


@router.get("/episodes/{eid}/character")
def get_character(eid: IdPath, db: DB):
    return repo.episode_to_out(_episode(db, eid))["character"]


@router.put("/episodes/{eid}/character")
def put_character(eid: IdPath, db: DB, payload: dict = Body(...)):
    ep = _episode(db, eid)
    repo.upsert_character(db, ep, _validate(s.CharacterIn, payload))
    ep.updated_at = repo.now_iso()
    db.commit()
    return repo.episode_to_out(ep)["character"]


@router.get("/episodes/{eid}/audits")
def get_audits(eid: IdPath, db: DB):
    _episode(db, eid)
    return run_audits(db, eid)


@router.get("/episodes/{eid}/receipt")
def get_receipt(eid: IdPath, db: DB):
    _episode(db, eid)
    return derive_receipt(db, eid)


# ---------- Episode-owned collections (generic) ----------
def _register_scoped(res: repo.Resource) -> None:
    base = f"/episodes/{{eid}}/{res.path}"

    @router.get(base, name=f"list_{res.collection}")
    def list_(eid: IdPath, db: DB):
        _episode(db, eid)
        return [repo.to_out(res, r) for r in db.scalars(select(res.model).where(res.model.episode_id == eid))]

    @router.post(base, status_code=201, name=f"create_{res.collection}")
    def create(eid: IdPath, db: DB, payload: dict = Body(...)):
        _episode(db, eid)
        payload = {**payload, "episodeId": eid}
        payload.setdefault("id", str(uuid.uuid4()))
        obj = _validate(res.schema, payload)
        if db.get(res.model, obj.id):
            raise HTTPException(409, f"{res.collection} record {obj.id} already exists")
        row = repo.upsert(db, res, obj)
        db.commit()
        return repo.to_out(res, row)

    @router.get(base + "/{rid}", name=f"get_{res.collection}")
    def get(eid: IdPath, rid: IdPath, db: DB):
        row = db.get(res.model, rid)
        if row is None or row.episode_id != eid:
            raise HTTPException(404, f"{res.collection} record {rid} not found")
        return repo.to_out(res, row)

    @router.put(base + "/{rid}", name=f"put_{res.collection}")
    def put(eid: IdPath, rid: IdPath, db: DB, payload: dict = Body(...)):
        _episode(db, eid)
        existing = db.get(res.model, rid)
        if existing is not None and existing.episode_id != eid:
            raise HTTPException(409, "Record belongs to another episode")
        obj = _validate(res.schema, {**payload, "id": rid, "episodeId": eid})
        if res.collection == "facts" and obj.source_id and db.get(m.Source, obj.source_id) is None:
            raise HTTPException(422, f"Source {obj.source_id} does not exist")
        if res.collection == "facts" and existing is not None and existing.value != obj.value and \
                db.scalar(select(m.CalculationInput).where(m.CalculationInput.fact_id == rid)) is not None:
            raise HTTPException(409, "This fact is an input to a saved calculation; its value cannot be changed.")
        if res.collection == "facts" and obj.external_observation_id and db.get(m.ExternalObservation, obj.external_observation_id) is None:
            raise HTTPException(422, "Linked observation does not exist")
        row = repo.upsert(db, res, obj)
        db.commit()
        return repo.to_out(res, row)

    @router.patch(base + "/{rid}", name=f"patch_{res.collection}")
    def patch(eid: IdPath, rid: IdPath, db: DB, payload: dict = Body(...)):
        row = db.get(res.model, rid)
        if row is None or row.episode_id != eid:
            raise HTTPException(404, f"{res.collection} record {rid} not found")
        obj = _validate(res.schema, {**repo.to_out(res, row), **payload, "id": rid, "episodeId": eid})
        row = repo.upsert(db, res, obj)
        db.commit()
        return repo.to_out(res, row)

    @router.delete(base + "/{rid}", status_code=204, name=f"delete_{res.collection}")
    def delete(eid: IdPath, rid: IdPath, db: DB):
        row = db.get(res.model, rid)
        if row is None or row.episode_id != eid:
            raise HTTPException(404, f"{res.collection} record {rid} not found")
        if res.collection == "facts" and db.scalar(select(m.CalculationInput).where(m.CalculationInput.fact_id == rid)) is not None:
            raise HTTPException(409, "This fact is an input to a saved calculation; delete the derived fact first.")
        db.delete(row)
        db.commit()


for _r in repo.RESOURCES:
    _register_scoped(_r)


# ---------- Global source registry ----------
SRC = repo.SOURCES


@router.get("/sources")
def list_sources(db: DB):
    return [repo.to_out(SRC, r) for r in db.scalars(select(m.Source))]


@router.post("/sources", status_code=201)
def create_source(db: DB, payload: dict = Body(...)):
    payload.setdefault("id", f"SRC-{uuid.uuid4().hex[:8]}")
    obj = _validate(s.SourceIn, payload)
    if db.get(m.Source, obj.id):
        raise HTTPException(409, "Source already exists")
    row = repo.upsert(db, SRC, obj)
    db.commit()
    return repo.to_out(SRC, row)


@router.get("/sources/{rid}")
def get_source(rid: IdPath, db: DB):
    row = db.get(m.Source, rid)
    if row is None:
        raise HTTPException(404, f"Source {rid} not found")
    return repo.to_out(SRC, row)


@router.put("/sources/{rid}")
def put_source(rid: IdPath, db: DB, payload: dict = Body(...)):
    row = repo.upsert(db, SRC, _validate(s.SourceIn, {**payload, "id": rid}))
    db.commit()
    return repo.to_out(SRC, row)


@router.delete("/sources/{rid}", status_code=204)
def delete_source(rid: IdPath, db: DB):
    row = db.get(m.Source, rid)
    if row is None:
        raise HTTPException(404, f"Source {rid} not found")
    db.delete(row)
    db.commit()
