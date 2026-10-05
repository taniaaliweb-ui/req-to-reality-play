"""Local LifeSpan MCP server (stdio, JSON-RPC 2.0, Model Context Protocol). Free, local, dependency-free.

Run:  python -m app.mcp_server        (from backend/, same LIFESPAN_DATA_DIR as the API)
Client config example (any MCP client):  {"command": "python", "args": ["-m", "app.mcp_server"], "cwd": "<repo>/backend"}

Write safety: tools call the same application services as the REST API. There is NO tool that edits snapshots,
verifies evidence, bypasses the Fact Ledger or audits, or runs SQL. Candidate evidence is always PENDING_REVIEW."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

SERVER_NAME, SERVER_VERSION = "lifespan", "0.6.0"
PROTOCOLS = ["2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28"]

S = {"type": "string"}
I = {"type": "integer"}
TOOLS = {
    "list_episodes": ("List episodes", {}),
    "get_episode": ("Episode with character", {"episodeId": S}),
    "get_character": ("Character DNA", {"episodeId": S}),
    "get_evidence_gaps": ("Open evidence gaps", {"episodeId": S}),
    "get_research_tasks": ("Open research tasks and gaps", {"episodeId": S}),
    "submit_candidate_evidence": ("Submit research for HUMAN review (always PENDING_REVIEW)",
                                  {"episodeId": S, "claim": S, "value": S, "unit": S, "location": S, "periodStart": I, "periodEnd": I, "source": S, "url": S, "notes": S}),
    "add_assumption": ("Add an explicit, labelled assumption to the episode's register (affects simulations only after a new snapshot)",
                       {"episodeId": S, "domain": S, "lifeStage": S, "claim": S, "value": S, "unit": S, "reason": S, "yearStart": I, "yearEnd": I}),
    "get_snapshot": ("Dataset snapshot summary (read-only; finalized snapshots are immutable)", {"snapshotId": S}),
    "run_simulation": ("Run one life from an existing frozen SimulationInput", {"inputId": S, "seed": I}),
    "get_simulation": ("Simulation run with outcome and quality report", {"runId": S}),
    "list_simulations": ("Simulation runs for an episode", {"episodeId": S}),
    "select_canonical_life": ("Set a run as the episode's canonical life", {"runId": S}),
    "get_timeline": ("Timeline events (FACTUAL / USER_LOCKED / SIMULATED / HISTORICAL_CONTEXT)", {"episodeId": S}),
    "run_audit": ("Simulation audit of a run", {"runId": S}),
    "get_story": ("Structured story (canonical life)", {"episodeId": S}),
    "get_production": ("Production workspace (scenes + script)", {"episodeId": S}),
    "get_life_receipt": ("Life Receipt 2.0", {"episodeId": S}),
}
REQUIRED = {"get_episode": ["episodeId"], "get_character": ["episodeId"], "get_evidence_gaps": ["episodeId"], "submit_candidate_evidence": ["claim", "source"],
            "add_assumption": ["episodeId", "domain", "lifeStage", "claim", "reason"], "get_snapshot": ["snapshotId"], "run_simulation": ["inputId"],
            "get_simulation": ["runId"], "list_simulations": ["episodeId"], "select_canonical_life": ["runId"], "get_timeline": ["episodeId"], "run_audit": ["runId"],
            "get_story": ["episodeId"], "get_production": ["episodeId"], "get_life_receipt": ["episodeId"]}


class ToolError(Exception):
    pass


def provenance(e) -> str:
    if e.simulation_run_id:
        return "SIMULATED"
    if e.locked:
        return "USER_LOCKED"
    if e.category == "External":
        return "HISTORICAL_CONTEXT"
    if e.fact_ids:
        return "FACTUAL"
    return "PROTOTYPE"


def call_tool(name: str, a: dict) -> object:
    from sqlalchemy import select

    from app.db import models as m
    from app.db.database import SessionLocal
    from app.services import repository as repo
    from app.services import snapshots as snaps
    from app.simulation import product
    from app.simulation import run as sim_run
    if name not in TOOLS:
        raise ToolError(f"Unknown or forbidden tool: {name}")
    for k in REQUIRED.get(name, []):
        if a.get(k) in (None, ""):
            raise ToolError(f"Missing argument {k}")
    with SessionLocal() as db:
        def ep():
            e = db.get(m.Episode, a["episodeId"])
            if e is None:
                raise ToolError("Episode not found")
            return e
        if name == "list_episodes":
            return [{"id": e.id, "title": e.title, "stage": e.stage, "isPrototype": e.is_mock} for e in db.scalars(select(m.Episode))]
        if name == "get_episode":
            return repo.episode_to_out(ep())
        if name == "get_character":
            return repo.episode_to_out(ep())["character"]
        if name == "get_evidence_gaps":
            ep()
            return [{"id": g.id, "title": g.title, "reason": g.reason, "priority": g.priority, "status": g.status}
                    for g in db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == a["episodeId"], m.EvidenceGap.status == "open"))]
        if name == "get_research_tasks":
            q = select(m.ResearchTask).where(m.ResearchTask.status == "open")
            if a.get("episodeId"):
                q = q.where(m.ResearchTask.episode_id == a["episodeId"])
            return [{"id": t.id, "episodeId": t.episode_id, "question": t.question, "category": t.category, "period": t.period} for t in db.scalars(q)]
        if name == "submit_candidate_evidence":
            from app.api.routers.simulation import CandidateIn, candidate_out, submit_candidate
            body = {k: a[k] for k in ("episodeId", "claim", "value", "unit", "location", "periodStart", "periodEnd", "source", "url", "notes") if k in a}
            return candidate_out(submit_candidate(db, CandidateIn(**body, submittedBy="mcp-agent")))  # status forced to PENDING_REVIEW
        if name == "add_assumption":
            from app.services import life_context as life
            ep()
            if a["lifeStage"] not in life.STAGE_LABEL:
                raise ToolError("Unknown life stage: " + ", ".join(life.STAGE_LABEL))
            ts = repo.now_iso()
            x = m.Assumption(id="ASM-" + uuid.uuid4().hex[:8], episode_id=a["episodeId"], domain=a["domain"], life_stage=a["lifeStage"], claim=a["claim"],
                             value=a.get("value", ""), unit=a.get("unit", ""), year_start=a.get("yearStart"), year_end=a.get("yearEnd"), reason=a["reason"],
                             created_by="mcp-agent", supporting_evidence=[], confidence="LOW", status="active", created_at=ts, updated_at=ts)
            db.add(x)
            db.commit()
            return life.assumption_out(x)
        if name == "get_snapshot":
            s = db.get(m.EpisodeDatasetSnapshot, a["snapshotId"])
            if s is None:
                raise ToolError("Snapshot not found")
            return snaps.summary(db, s)
        if name == "run_simulation":
            try:
                return sim_run.run_out(sim_run.run_life(db, a["inputId"], a.get("seed"), label="via MCP"))
            except (LookupError, sim_run.RunError) as e:
                raise ToolError(str(e)) from e
        if name in ("get_simulation", "run_audit", "select_canonical_life"):
            r = db.get(m.LifeSimulationRun, a["runId"])
            if r is None:
                raise ToolError("Run not found")
            if name == "run_audit":
                return {"runId": r.id, "audit": r.audit, "qualityReport": r.quality_report}
            if name == "select_canonical_life":
                r = sim_run.set_canonical(db, r.id)
            out = sim_run.run_out(r)
            out.pop("finalState", None)
            return out
        if name == "list_simulations":
            return [{"id": r.id, "kind": r.kind, "seed": r.seed, "isCanonical": r.is_canonical, "deathAge": r.outcome.get("deathAge")}
                    for r in db.scalars(select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == a["episodeId"], m.LifeSimulationRun.kind != "batch"))]
        if name == "get_timeline":
            ep()
            return [{"id": e.id, "year": e.year, "age": e.age, "title": e.title, "category": e.category, "locked": e.locked, "provenance": provenance(e)}
                    for e in db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.episode_id == a["episodeId"]).order_by(m.TimelineEvent.year))]
        try:
            if name == "get_story":
                st = product.story(db, a["episodeId"])
                return {"label": st["label"], "chapters": [{"title": c["title"], "draft": c["draft"]} for c in st["chapters"]], "audit": st.get("audit")}
            if name == "get_production":
                p = product.production(db, a["episodeId"])
                return {"summary": p["summary"], "scenes": len(p["scenes"]), "check": p["check"], "script": p["script"][:20000]}
            if name == "get_life_receipt":
                return product.receipt(db, a["episodeId"])
        except product.ProductError as e:
            raise ToolError(str(e)) from e
    raise ToolError("unreachable")


def _schema(name):
    props = TOOLS[name][1]
    return {"type": "object", "properties": props, "required": REQUIRED.get(name, []), "additionalProperties": False}


def handle(msg: dict) -> dict | None:
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:
        return None  # notification
    if method == "initialize":
        pv = params.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": pv if pv in PROTOCOLS else PROTOCOLS[-2], "capabilities": {"tools": {"listChanged": False}},
                                                       "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [{"name": n, "description": d, "inputSchema": _schema(n)} for n, (d, _) in TOOLS.items()]}}
    if method == "tools/call":
        try:
            res = call_tool(params.get("name"), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(res, default=str)}], "isError": False}}
        except ToolError as e:
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": str(e)}], "isError": True}}
        except Exception as e:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"Internal error: {type(e).__name__}"}], "isError": True}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    from app.db.migrate import upgrade_to_head
    upgrade_to_head()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        out = handle(msg)
        if out is not None:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()


def self_test(timeout: float = 20.0) -> dict:
    """Real client handshake against a spawned server process: initialize → tools/list → tools/call(list_episodes)."""
    backend = Path(__file__).resolve().parents[1]
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "lifespan-selftest", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_episodes", "arguments": {}}}]
    try:
        p = subprocess.run([sys.executable, "-m", "app.mcp_server"], input="\n".join(json.dumps(r) for r in reqs) + "\n", capture_output=True, text=True,
                           cwd=backend, env={**os.environ, "PYTHONPATH": str(backend)}, timeout=timeout)
        lines = [json.loads(x) for x in p.stdout.splitlines() if x.strip()]
        tools = next((x["result"]["tools"] for x in lines if x.get("id") == 2), [])
        call = next((x["result"] for x in lines if x.get("id") == 3), None)
        ok = bool(tools) and call is not None and not call.get("isError")
        return {"status": "AVAILABLE" if ok else "ERROR", "transport": "stdio", "command": "python -m app.mcp_server", "cwd": str(backend),
                "tools": [t["name"] for t in tools], "detail": "Local client handshake succeeded" if ok else (p.stderr[-500:] or "handshake failed"),
                "aiIntegrations": "None connected (ChatGPT / Hermes / Claude integrations are not claimed)."}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERROR", "detail": str(e)[:500], "tools": []}


if __name__ == "__main__":
    main()
