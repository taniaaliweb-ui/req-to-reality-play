"""AI orchestration interface — PREPARED, NOT ACTIVE.

Future flow: strong supervisor → task planning → lower-cost/local workers → results → supervisor verification
→ accept / retry / escalate. Every provider is NOT_CONFIGURED; no job is ever processed and no result is ever
fabricated. External agents may only submit CandidateEvidence (PENDING_REVIEW) — never verify their own work."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services.repository import now_iso

ROLES = ["SUPERVISOR", "RESEARCHER", "EXTRACTOR", "FACT_CHECKER", "SIMULATION_CRITIC", "STORY_WRITER", "STORY_CRITIC", "PRODUCTION_ASSISTANT"]
PROVIDERS = ["LOCAL", "OPENAI", "HERMES", "ANTHROPIC", "GOOGLE", "CUSTOM"]


def status() -> dict:
    return {"active": False, "defaultProvider": "NOT_CONFIGURED", "roles": [{"role": r, "provider": "NOT_CONFIGURED"} for r in ROLES],
            "providers": [{"provider": p, "status": "DISCONNECTED", "required": False} for p in PROVIDERS],
            "flow": ["SUPERVISOR plans tasks", "workers (local / low-cost) execute", "SUPERVISOR verifies", "accept / retry / escalate"],
            "note": "Prepared interface only. LifeSpan's core works fully without any AI provider."}


def job_out(j: m.AgentJob) -> dict:
    return {"id": j.id, "role": j.role, "task": j.task, "parentId": j.parent_id, "input": j.input, "result": j.result, "status": j.status, "provider": j.provider,
            "model": j.model, "error": j.error, "createdAt": j.created_at, "updatedAt": j.updated_at}


def create_job(db: Session, role: str, task: str, inp: dict | None = None, parent_id: str | None = None) -> m.AgentJob:
    if role not in ROLES:
        raise ValueError(f"Unknown role {role}")
    ts = now_iso()
    j = m.AgentJob(id="AJ-" + uuid.uuid4().hex[:10], role=role, task=task, parent_id=parent_id, input=inp or {}, result=None, status="QUEUED",
                   provider="NOT_CONFIGURED", model="", error="No provider configured — this job will not run until an optional provider is connected.",
                   created_at=ts, updated_at=ts)
    db.add(j)
    db.commit()
    return j


def list_jobs(db: Session) -> list[m.AgentJob]:
    return list(db.scalars(select(m.AgentJob).order_by(m.AgentJob.created_at.desc()).limit(200)))
