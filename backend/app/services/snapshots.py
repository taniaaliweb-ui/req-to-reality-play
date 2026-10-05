"""Episode Dataset Snapshots: freeze exactly which facts, observations (with their values at that
moment) and baselines an episode relies on. Finalized snapshots are immutable — enforced here and by
SQLite triggers — and are verified by a content hash. Changes create a new version."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services import labor
from app.services.repository import now_iso
from app.services.truth import obs_out


class SnapshotError(ValueError):
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


def _fact_payload(f: m.Fact) -> dict:
    return {"id": f.id, "metric": f.metric, "value": f.value, "unit": f.unit, "factType": f.fact_type, "status": f.status, "country": f.country,
            "region": f.region, "yearStart": f.year_start, "yearEnd": f.year_end, "sourceId": f.source_id, "confidence": f.confidence,
            "externalObservationId": f.external_observation_id, "provider": f.provider, "currency": f.currency, "derivedFrom": f.derived_from,
            "notes": f.notes, "updatedAt": f.updated_at}


def _collect(db: Session, episode_id: str) -> tuple[list[tuple], list[tuple], list[tuple], int]:
    all_facts = list(db.scalars(select(m.Fact).where(m.Fact.episode_id == episode_id)))
    facts = [f for f in all_facts if not f.is_prototype]
    excluded = len(all_facts) - len(facts)
    baselines = list(db.scalars(select(m.EconomicBaseline).where(m.EconomicBaseline.episode_id == episode_id)))
    obs_ids = {f.external_observation_id for f in facts if f.external_observation_id}
    for b in baselines:
        obs_ids |= {e["observationId"] for e in b.evidence or []}
    obs = [db.get(m.ExternalObservation, i) for i in sorted(obs_ids)]
    F = [(f.id, f.updated_at, _fact_payload(f)) for f in sorted(facts, key=lambda x: x.id)]
    O = [(o.id, o.value, o.retrieved_at, {k: v for k, v in obs_out(o).items() if k != "rawMetadata"}) for o in obs if o is not None]
    B = [(b.id, labor.baseline_out(db, b)) for b in sorted(baselines, key=lambda x: x.id)]
    for _, p in B:
        p.pop("pinnedInSnapshot", None)
    return F, O, B, excluded


def _write_contents(db: Session, sid: str, episode_id: str):
    F, O, B, excluded = _collect(db, episode_id)
    for t in (m.SnapshotFact, m.SnapshotObservation, m.SnapshotBaseline):
        for r in db.scalars(select(t).where(t.snapshot_id == sid)):
            db.delete(r)
    db.flush()
    for fid, upd, p in F:
        db.add(m.SnapshotFact(snapshot_id=sid, fact_id=fid, fact_updated_at=upd, payload=p))
    for oid, val, ret, p in O:
        db.add(m.SnapshotObservation(snapshot_id=sid, external_observation_id=oid, value=val, retrieved_at=ret, payload=p))
    for bid, p in B:
        db.add(m.SnapshotBaseline(snapshot_id=sid, economic_baseline_id=bid, payload=p))
    snap = db.get(m.EpisodeDatasetSnapshot, sid)
    snap.items = [{"observationId": oid, "value": val, "retrievedAt": ret} for oid, val, ret, _ in O]
    snap.notes = snap.notes  # unchanged
    return excluded


def content_hash(db: Session, sid: str) -> str:
    F = [(r.fact_id, r.fact_updated_at, r.payload) for r in db.scalars(select(m.SnapshotFact).where(m.SnapshotFact.snapshot_id == sid).order_by(m.SnapshotFact.fact_id))]
    O = [(r.external_observation_id, r.value, r.retrieved_at) for r in db.scalars(select(m.SnapshotObservation).where(m.SnapshotObservation.snapshot_id == sid)
                                                                                  .order_by(m.SnapshotObservation.external_observation_id))]
    B = [(r.economic_baseline_id, r.payload) for r in db.scalars(select(m.SnapshotBaseline).where(m.SnapshotBaseline.snapshot_id == sid).order_by(m.SnapshotBaseline.economic_baseline_id))]
    return hashlib.sha256(json.dumps([F, O, B], sort_keys=True, default=str).encode()).hexdigest()


def summary(db: Session, s: m.EpisodeDatasetSnapshot) -> dict:
    facts = list(db.scalars(select(m.SnapshotFact).where(m.SnapshotFact.snapshot_id == s.id)))
    obs = list(db.scalars(select(m.SnapshotObservation).where(m.SnapshotObservation.snapshot_id == s.id)))
    bls = list(db.scalars(select(m.SnapshotBaseline).where(m.SnapshotBaseline.snapshot_id == s.id)))
    by_type = Counter(f.payload.get("factType") for f in facts)
    verified = sum(1 for f in facts if f.payload.get("status") == "verified" and f.payload.get("factType") in ("FACT", "DERIVED"))
    by_provider = Counter((o.payload or {}).get("provider") or o.external_observation_id.split(":")[0] for o in obs)
    intact = None
    if s.status == "final" and s.content_hash:
        intact = content_hash(db, s.id) == s.content_hash
    return {"id": s.id, "episodeId": s.episode_id, "name": s.label, "status": s.status, "version": s.version, "parentId": s.parent_id, "notes": s.notes,
            "createdAt": s.created_at, "finalizedAt": s.finalized_at, "contentHash": s.content_hash, "intact": intact,
            "counts": {"facts": len(facts), "verifiedFacts": verified, "assumptions": by_type.get("ASSUMPTION", 0), "derived": by_type.get("DERIVED", 0),
                       "observations": len(obs), "observationsByProvider": dict(by_provider), "baselines": len(bls),
                       "approvedBaselines": sum(1 for b in bls if b.payload.get("userApproved"))}}


def detail(db: Session, s: m.EpisodeDatasetSnapshot) -> dict:
    return {**summary(db, s),
            "facts": [r.payload for r in db.scalars(select(m.SnapshotFact).where(m.SnapshotFact.snapshot_id == s.id).order_by(m.SnapshotFact.fact_id))],
            "observations": [{**r.payload, "value": r.value, "retrievedAt": r.retrieved_at} for r in db.scalars(
                select(m.SnapshotObservation).where(m.SnapshotObservation.snapshot_id == s.id).order_by(m.SnapshotObservation.external_observation_id))],
            "baselines": [r.payload for r in db.scalars(select(m.SnapshotBaseline).where(m.SnapshotBaseline.snapshot_id == s.id))]}


def _base_name(name: str) -> str:
    return re.sub(r"\s+v\d+$", "", name.strip())


def create(db: Session, episode_id: str, name: str, notes: str = "", parent: m.EpisodeDatasetSnapshot | None = None) -> m.EpisodeDatasetSnapshot:
    base = _base_name(name)
    versions = [s.version for s in db.scalars(select(m.EpisodeDatasetSnapshot).where(m.EpisodeDatasetSnapshot.episode_id == episode_id))
                if _base_name(s.label) == base]
    ver = (max(versions) + 1) if versions else 1
    s = m.EpisodeDatasetSnapshot(id="SNAP-" + uuid.uuid4().hex[:10], episode_id=episode_id, label=f"{base} v{ver}", created_at=now_iso(), items=[],
                                 status="draft", notes=notes, version=ver, parent_id=parent.id if parent else None)
    db.add(s)
    db.flush()
    _write_contents(db, s.id, episode_id)
    db.commit()
    return s


def refresh(db: Session, s: m.EpisodeDatasetSnapshot) -> None:
    if s.status == "final":
        raise SnapshotError(409, "Snapshot is finalized and immutable. Create a new version instead.")
    _write_contents(db, s.id, s.episode_id)
    db.commit()


def finalize(db: Session, s: m.EpisodeDatasetSnapshot) -> None:
    if s.status == "final":
        raise SnapshotError(409, "Snapshot is already finalized.")
    s.content_hash = content_hash(db, s.id)
    s.finalized_at = now_iso()
    s.status = "final"
    db.commit()


def delete(db: Session, s: m.EpisodeDatasetSnapshot) -> None:
    if s.status == "final":
        raise SnapshotError(409, "Finalized snapshots cannot be deleted.")
    db.delete(s)
    db.commit()


def diff(db: Session, a: m.EpisodeDatasetSnapshot, b: m.EpisodeDatasetSnapshot) -> dict:
    da, dbb = detail(db, a), detail(db, b)

    def cmp(xs, ys, key, val, label):
        A, B = {x[key]: x for x in xs}, {y[key]: y for y in ys}
        out = []
        for k in sorted(set(A) | set(B)):
            if k not in A:
                out.append({"kind": "added", "id": k, "label": label(B[k]), "new": val(B[k])})
            elif k not in B:
                out.append({"kind": "removed", "id": k, "label": label(A[k]), "old": val(A[k])})
            elif val(A[k]) != val(B[k]):
                out.append({"kind": "changed", "id": k, "label": label(B[k]), "old": val(A[k]), "new": val(B[k])})
            else:
                out.append({"kind": "unchanged", "id": k, "label": label(B[k]), "old": val(A[k])})
        return out

    rng = lambda p: p.get("point") or f"{p.get('low')}–{p.get('high')}"  # noqa: E731
    return {"from": summary(db, a), "to": summary(db, b),
            "observations": cmp(da["observations"], dbb["observations"], "id", lambda o: o["value"], lambda o: f"{o.get('countryCode')} {o.get('year')} {o.get('indicatorName') or o.get('indicatorCode')}"),
            "facts": cmp(da["facts"], dbb["facts"], "id", lambda f: f["value"], lambda f: f["metric"]),
            "baselines": cmp(da["baselines"], dbb["baselines"], "id", lambda p: f"{rng(p)} {p.get('currency')}/{(p.get('payPeriod') or '').lower()} · {p.get('baselineType')}",
                             lambda p: f"{p.get('lifeStageLabel')} {p.get('yearStart')}–{p.get('yearEnd')}")}


def list_for(db: Session, episode_id: str) -> list[dict]:
    return [summary(db, s) for s in db.scalars(select(m.EpisodeDatasetSnapshot).where(m.EpisodeDatasetSnapshot.episode_id == episode_id)
                                               .order_by(m.EpisodeDatasetSnapshot.created_at.desc()))]


_ = func
