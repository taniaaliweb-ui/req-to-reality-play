"""Seeds the PROTOTYPE demo episode exactly once (guarded by a meta marker).
All values in demo_episode.json are mock/illustrative and unverified."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import models as m
from app.schemas.records import Snapshot
from app.services.repository import import_snapshot

log = logging.getLogger("lifespan")
SEED_FILE = Path(__file__).with_name("demo_episode.json")
MARKER = "demo_seed_v1"


def seed_demo(db: Session) -> bool:
    if db.get(m.Meta, MARKER) is not None:
        return False
    snap = Snapshot.model_validate(json.loads(SEED_FILE.read_text()))
    report = import_snapshot(db, snap, overwrite=False)
    db.add(m.Meta(key=MARKER, value={"report": {k: v for k, v in report.items() if k != "conflicts"}}))
    db.commit()
    log.info("Seeded PROTOTYPE demo episode (%s records)", report["created"])
    return True
