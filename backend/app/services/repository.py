"""Persistence services. Routers call these; they never touch SQL directly."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.schemas import records as s


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Resource:
    collection: str  # key in Snapshot / frontend LifespanDB
    path: str  # URL segment
    model: type
    schema: type[s.Schema]
    scoped: bool  # belongs to an episode
    stamped: bool = True


RESOURCES: list[Resource] = [
    Resource("tasks", "research-tasks", m.ResearchTask, s.ResearchTaskIn, True),
    Resource("facts", "facts", m.Fact, s.FactIn, True),
    Resource("timeline", "timeline", m.TimelineEvent, s.TimelineEventIn, True),
    Resource("economics", "economic-years", m.EconomicYear, s.EconomicYearIn, True, stamped=False),
    Resource("simulations", "simulations", m.SimulationRun, s.SimulationRunIn, True),
    Resource("chapters", "story", m.StoryChapter, s.StoryChapterIn, True),
]
SOURCES = Resource("sources", "sources", m.Source, s.SourceIn, False)
BY_COLLECTION = {r.collection: r for r in [*RESOURCES, SOURCES]}


def to_out(res: Resource, row: Any) -> dict:
    return res.schema.model_validate(row).out()


def _fields(schema_obj: s.Schema) -> dict:
    return schema_obj.model_dump(by_alias=False)


def upsert(db: Session, res: Resource, obj: s.Schema, *, keep_created: bool = True) -> Any:
    data = _fields(obj)
    row = db.get(res.model, data["id"])
    ts = now_iso()
    if res.stamped:
        data["updated_at"] = ts
        if row is not None and keep_created:
            data["created_at"] = row.created_at
        elif not data.get("created_at"):
            data["created_at"] = ts
    if row is None:
        row = res.model(**data)
        db.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    return row


def episode_to_out(ep: m.Episode) -> dict:
    out = s.EpisodeIn.model_validate(
        {
            "id": ep.id, "created_at": ep.created_at, "updated_at": ep.updated_at, "title": ep.title,
            "stage": ep.stage, "is_mock": ep.is_mock, "character": s.CharacterIn.model_validate(ep.character).model_dump(),
        }
    )
    return out.out()


def upsert_episode(db: Session, obj: s.EpisodeIn) -> m.Episode:
    ts = now_iso()
    ep = db.get(m.Episode, obj.id)
    if ep is None:
        ep = m.Episode(id=obj.id, created_at=obj.created_at or ts, updated_at=ts, title=obj.title, stage=obj.stage, is_mock=obj.is_mock)
        db.add(ep)
    else:
        ep.title, ep.stage, ep.is_mock, ep.updated_at = obj.title, obj.stage, obj.is_mock, ts
    upsert_character(db, ep, obj.character)
    return ep


def upsert_character(db: Session, ep: m.Episode, c: s.CharacterIn) -> m.Character:
    data = c.model_dump()
    data["updated_at"] = now_iso()
    data["created_at"] = data.get("created_at") or data["updated_at"]
    row = ep.character or db.scalar(select(m.Character).where(m.Character.episode_id == ep.id))
    if row is None:
        row = m.Character(episode_id=ep.id, **data)
        db.add(row)
        ep.character = row
    else:
        data.pop("id")
        for k, v in data.items():
            setattr(row, k, v)
    return row


DEFAULT_SETTINGS = s.SettingsIn().out()


def get_settings(db: Session) -> dict:
    row = db.get(m.Meta, "settings")
    return s.SettingsIn.model_validate({**DEFAULT_SETTINGS, **(row.value if row else {})}).out()


def put_settings(db: Session, obj: s.SettingsIn) -> dict:
    row = db.get(m.Meta, "settings")
    if row is None:
        db.add(m.Meta(key="settings", value=obj.out()))
    else:
        row.value = obj.out()
    return obj.out()


def snapshot(db: Session) -> dict:
    out: dict[str, Any] = {"version": 1}
    out["episodes"] = [episode_to_out(e) for e in db.scalars(select(m.Episode).order_by(m.Episode.created_at.desc()))]
    for res in [*RESOURCES, SOURCES]:
        out[res.collection] = [to_out(res, r) for r in db.scalars(select(res.model))]
    out["activity"] = [s.ActivityIn.model_validate(a).out() for a in db.scalars(select(m.Activity).order_by(m.Activity.at.desc()).limit(50))]
    out["settings"] = get_settings(db)
    return out


def import_snapshot(db: Session, snap: s.Snapshot, overwrite: bool) -> dict:
    """Import a full workspace (e.g. Phase 1 browser data). Existing records are skipped unless overwrite."""
    report = {"created": 0, "updated": 0, "skipped": 0, "conflicts": []}

    def handle(exists: bool, label: str, write):
        if exists and not overwrite:
            report["skipped"] += 1
            report["conflicts"].append(label)
            return
        write()
        report["updated" if exists else "created"] += 1

    for src in snap.sources:
        handle(db.get(m.Source, src.id) is not None, f"source:{src.id}", lambda src=src: upsert(db, SOURCES, src))
    db.flush()
    for ep in snap.episodes:
        handle(db.get(m.Episode, ep.id) is not None, f"episode:{ep.id}", lambda ep=ep: upsert_episode(db, ep))
    db.flush()
    known = {e.id for e in db.scalars(select(m.Episode))}
    for res in RESOURCES:
        for rec in getattr(snap, res.collection):
            if rec.episode_id not in known:
                report["skipped"] += 1
                continue
            if res.collection == "facts" and rec.source_id and db.get(m.Source, rec.source_id) is None:
                rec = rec.model_copy(update={"source_id": None})
            handle(db.get(res.model, rec.id) is not None, f"{res.collection}:{rec.id}", lambda res=res, rec=rec: upsert(db, res, rec))
    for a in snap.activity:
        if db.get(m.Activity, a.id) is None:
            db.add(m.Activity(**a.model_dump()))
    db.commit()
    report["conflicts"] = report["conflicts"][:50]
    return report
