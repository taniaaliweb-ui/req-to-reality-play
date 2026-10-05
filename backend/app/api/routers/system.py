"""Health, workspace snapshot, import, settings and activity."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import SERVICE_NAME
from app.db import models as m
from app.db.database import get_db, ping
from app.schemas import records as s
from app.services import repository as repo

router = APIRouter()
DB = Annotated[Session, Depends(get_db)]


@router.get("/health")
def health():
    ok = ping()
    return {"status": "ok" if ok else "degraded", "service": SERVICE_NAME, "database": "connected" if ok else "unavailable", "databaseType": "sqlite"}


@router.get("/snapshot")
def get_snapshot(db: DB):
    return repo.snapshot(db)


@router.post("/import")
def import_data(db: DB, payload: dict = Body(...)):
    try:
        req = s.ImportRequest.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    return repo.import_snapshot(db, req.data, req.overwrite)


@router.get("/settings")
def get_settings(db: DB):
    return repo.get_settings(db)


@router.put("/settings")
def put_settings(db: DB, payload: dict = Body(...)):
    try:
        obj = s.SettingsIn.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    out = repo.put_settings(db, obj)
    db.commit()
    return out


@router.post("/activity", status_code=201)
def add_activity(db: DB, payload: dict = Body(...)):
    try:
        a = s.ActivityIn.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False)) from None
    if db.get(m.Activity, a.id) is None:
        db.add(m.Activity(**a.model_dump()))
        db.commit()
    return a.out()
