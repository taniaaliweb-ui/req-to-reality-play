"""Local LifeSpan MCP server (stdio, JSON-RPC 2.0, Model Context Protocol). Free, local, dependency-free.

Run:  python -m app.mcp_server        (from backend/, same LIFESPAN_DATA_DIR as the API)
Client config example (any MCP client):  {"command": "python", "args": ["-m", "app.mcp_server"], "cwd": "<repo>/backend"}

Write safety: tools call the same application services as the REST API. There is NO tool that edits snapshots,
verifies evidence, bypasses the Fact Ledger or audits, or runs SQL. Candidate evidence is always PENDING_REVIEW.

Permissions (Phase 6.1): every tool has a risk class READ / SAFE_WRITE / CONSEQUENTIAL_WRITE (PROHIBITED tools are never
exposed) and a group (Research, Evidence, Simulation, Story, Production, Administration). The user enables groups per profile
(default: external research agent → Research + Evidence) and chooses whether consequential writes REQUIRE_APPROVAL (default),
are ALLOWed, or DENYed. Pending approvals are decided in the LifeSpan UI."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

SERVER_NAME, SERVER_VERSION = "lifespan", "0.6.1"
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
            "get_story": ["episodeId"], "get_production": ["episodeId"], "get_life_receipt": ["episodeId"], "get_facts": ["episodeId"], "create_research_task": ["episodeId", "question", "category"],
            "change_model_prior": ["key"], "get_approval_status": ["approvalId"]}
TOOLS.update({
    "get_facts": ("Fact Ledger entries (read-only)", {"episodeId": S}),
    "create_research_task": ("Create an open research task (does not change any evidence)", {"episodeId": S, "question": S, "category": S, "period": S}),
    "change_model_prior": ("Propose a new version of a model prior (parameter JSON and/or enabled). Creates version n+1; never edits in place",
                           {"key": S, "parameter": {"type": "object"}, "enabled": {"type": "boolean"}, "notes": S}),
    "get_approval_status": ("Status/result of a CONSEQUENTIAL_WRITE call waiting for user approval", {"approvalId": S}),
    "get_mcp_permissions": ("This server's risk classes, enabled tool groups and approval mode", {}),
})

# ---------------------------------------------------------------- permission model
RISK = ("READ", "SAFE_WRITE", "CONSEQUENTIAL_WRITE", "PROHIBITED")
GROUPS = ("Research", "Evidence", "Simulation", "Story", "Production", "Administration")
TOOL_META: dict[str, tuple[str, str]] = {
    "list_episodes": ("READ", "Evidence"), "get_episode": ("READ", "Evidence"), "get_character": ("READ", "Evidence"), "get_facts": ("READ", "Evidence"),
    "get_snapshot": ("READ", "Evidence"), "get_evidence_gaps": ("READ", "Research"), "get_research_tasks": ("READ", "Research"),
    "submit_candidate_evidence": ("SAFE_WRITE", "Research"), "create_research_task": ("SAFE_WRITE", "Research"),
    "add_assumption": ("CONSEQUENTIAL_WRITE", "Evidence"), "get_simulation": ("READ", "Simulation"), "list_simulations": ("READ", "Simulation"),
    "get_timeline": ("READ", "Simulation"), "run_audit": ("READ", "Simulation"), "run_simulation": ("CONSEQUENTIAL_WRITE", "Simulation"),
    "select_canonical_life": ("CONSEQUENTIAL_WRITE", "Simulation"), "change_model_prior": ("CONSEQUENTIAL_WRITE", "Simulation"),
    "get_story": ("READ", "Story"), "get_production": ("READ", "Production"), "get_life_receipt": ("READ", "Production"),
    "get_approval_status": ("READ", "Administration"), "get_mcp_permissions": ("READ", "Administration"),
}
# Never exposed, never executable — listed so a request for them is answered explicitly.
PROHIBITED = {
    "modify_finalized_snapshot": "Finalized dataset snapshots are immutable (service check + database triggers + content hash).",
    "refresh_finalized_snapshot": "Finalized dataset snapshots are immutable; create a new version instead.",
    "delete_snapshot": "Snapshots cannot be deleted by an agent.",
    "execute_sql": "Direct database execution is prohibited.",
    "run_sql": "Direct database execution is prohibited.",
    "mark_research_verified": "External research can only be accepted by a human reviewer in the LifeSpan UI.",
    "review_candidate_evidence": "External research can only be accepted by a human reviewer in the LifeSpan UI.",
    "verify_fact": "Facts are verified only through human review.",
}
DEFAULT_CONFIG = {"profile": "external-research-agent", "enabledGroups": ["Research", "Evidence"], "consequential": "REQUIRE_APPROVAL"}
PROFILES = {"external-research-agent": ["Research", "Evidence"], "story-assistant": ["Evidence", "Story", "Production"],
            "simulation-operator": ["Evidence", "Simulation"], "full-local": list(GROUPS)}


def get_config(db) -> dict:
    from app.db import models as m
    row = db.get(m.Meta, "mcp-config")
    cfg = {**DEFAULT_CONFIG, **(row.value if row else {})}
    cfg["enabledGroups"] = [g for g in cfg.get("enabledGroups") or [] if g in GROUPS]
    if cfg.get("consequential") not in ("REQUIRE_APPROVAL", "ALLOW", "DENY"):
        cfg["consequential"] = "REQUIRE_APPROVAL"
    return cfg


def put_config(db, cfg: dict) -> dict:
    from app.db import models as m
    groups = [g for g in cfg.get("enabledGroups") or [] if g in GROUPS]
    mode = cfg.get("consequential", "REQUIRE_APPROVAL")
    if mode not in ("REQUIRE_APPROVAL", "ALLOW", "DENY"):
        raise ValueError("consequential must be REQUIRE_APPROVAL, ALLOW or DENY")
    val = {"profile": cfg.get("profile") or "custom", "enabledGroups": groups, "consequential": mode}
    row = db.get(m.Meta, "mcp-config")
    if row is None:
        db.add(m.Meta(key="mcp-config", value=val))
    else:
        row.value = val
    db.commit()
    return get_config(db)


def tool_catalogue(cfg: dict) -> list[dict]:
    out = [{"name": n, "description": TOOLS[n][0], "riskClass": r, "group": g, "enabled": tool_enabled(n, cfg)} for n, (r, g) in TOOL_META.items()]
    out += [{"name": n, "description": why, "riskClass": "PROHIBITED", "group": "—", "enabled": False} for n, why in PROHIBITED.items()]
    return out


def tool_enabled(name: str, cfg: dict) -> bool:
    if name not in TOOL_META:
        return False
    risk, group = TOOL_META[name]
    if group == "Administration":
        return True  # read-only status tools are always available
    if group not in cfg["enabledGroups"]:
        return False
    return not (risk == "CONSEQUENTIAL_WRITE" and cfg["consequential"] == "DENY")


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


def call_tool(name: str, a: dict, approved: bool = False) -> object:
    from sqlalchemy import select

    from app.db import models as m
    from app.db.database import SessionLocal
    from app.services import repository as repo
    from app.services import snapshots as snaps
    from app.simulation import product
    from app.simulation import run as sim_run
    if name in PROHIBITED:
        raise ToolError(f"PROHIBITED: {name} — {PROHIBITED[name]}")
    if name not in TOOLS or name not in TOOL_META:
        raise ToolError(f"Unknown or forbidden tool: {name}")
    for k in REQUIRED.get(name, []):
        if a.get(k) in (None, ""):
            raise ToolError(f"Missing argument {k}")
    with SessionLocal() as db:
        cfg = get_config(db)
        risk, group = TOOL_META[name]
        if not tool_enabled(name, cfg):
            raise ToolError(f"DISABLED: tool group '{group}' is not enabled for this MCP profile ({cfg['profile']}), or {risk} calls are denied. "
                            "The user can change this in LifeSpan → System Status → MCP permissions.")
        if risk == "CONSEQUENTIAL_WRITE" and cfg["consequential"] == "REQUIRE_APPROVAL" and not approved:
            ap = m.McpApproval(id="MCPA-" + uuid.uuid4().hex[:10], tool=name, arguments=a, status="PENDING", created_at=repo.now_iso())
            db.add(ap)
            db.commit()
            return {"status": "APPROVAL_REQUIRED", "approvalId": ap.id, "riskClass": risk,
                    "message": f"{name} is a CONSEQUENTIAL_WRITE. It will run only after the user approves {ap.id} in LifeSpan (System Status → MCP approvals). "
                               "Poll get_approval_status."}
        if name == "get_mcp_permissions":
            return {"config": cfg, "tools": tool_catalogue(cfg)}
        if name == "get_approval_status":
            ap = db.get(m.McpApproval, a["approvalId"])
            if ap is None:
                raise ToolError("Approval not found")
            return {"id": ap.id, "tool": ap.tool, "status": ap.status, "result": ap.result}
        if name == "get_facts":
            ep_ = db.get(m.Episode, a["episodeId"])
            if ep_ is None:
                raise ToolError("Episode not found")
            return [{"id": f.id, "metric": f.metric, "value": f.value, "unit": f.unit, "country": f.country, "years": [f.year_start, f.year_end],
                     "factType": f.fact_type, "status": f.status, "sourceId": f.source_id, "isPrototype": f.is_prototype}
                    for f in db.scalars(select(m.Fact).where(m.Fact.episode_id == a["episodeId"]))]
        if name == "create_research_task":
            if db.get(m.Episode, a["episodeId"]) is None:
                raise ToolError("Episode not found")
            cats = ["Demographics", "Economy", "Employment", "Housing", "Education", "Migration", "Social environment", "Historical context"]
            if a["category"] not in cats:
                raise ToolError("category must be one of " + ", ".join(cats))
            ts = repo.now_iso()
            t = m.ResearchTask(id="RT-" + uuid.uuid4().hex[:8], episode_id=a["episodeId"], category=a["category"], question=str(a["question"])[:2000],
                               period=str(a.get("period") or "")[:60], status="pending", assigned_to="mcp-agent", fact_ids=[], created_at=ts, updated_at=ts)
            db.add(t)
            db.commit()
            return {"id": t.id, "status": t.status, "question": t.question}
        if name == "change_model_prior":
            from app.simulation import priors as pri
            try:
                p = pri.update(db, a["key"], repo.now_iso(), parameter=a.get("parameter"), enabled=a.get("enabled"),
                               notes=(a.get("notes") or "") + " [changed via MCP after user approval]")
            except (LookupError, ValueError) as e:
                raise ToolError(str(e)) from e
            return pri.prior_out(p)
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


def execute_approval(approval_id: str, approve: bool) -> dict:
    """Called from the LifeSpan UI (REST) — the user's explicit decision. Approved calls run once, through the same services."""
    from app.db import models as m
    from app.db.database import SessionLocal
    from app.services import repository as repo
    with SessionLocal() as db:
        ap = db.get(m.McpApproval, approval_id)
        if ap is None:
            raise LookupError("Approval not found")
        if ap.status != "PENDING":
            raise ValueError(f"Approval already {ap.status}")
        ap.decided_at = repo.now_iso()
        if not approve:
            ap.status = "REJECTED"
            db.commit()
            return approval_out(ap)
        tool, args = ap.tool, dict(ap.arguments)
        db.commit()
    try:
        res, status = json.loads(json.dumps(call_tool(tool, args, approved=True), default=str)), "EXECUTED"
    except ToolError as e:
        res, status = {"error": str(e)}, "FAILED"
    with SessionLocal() as db:
        ap = db.get(m.McpApproval, approval_id)
        ap.status, ap.result = status, res if isinstance(res, dict) else {"result": res}
        db.commit()
        return approval_out(ap)


def approval_out(ap) -> dict:
    return {"id": ap.id, "tool": ap.tool, "arguments": ap.arguments, "status": ap.status, "result": ap.result, "createdAt": ap.created_at,
            "decidedAt": ap.decided_at, "riskClass": TOOL_META.get(ap.tool, ("?", ""))[0]}


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
        from app.db.database import SessionLocal
        with SessionLocal() as db:
            cfg = get_config(db)
        tools = [{"name": n, "description": f"[{TOOL_META[n][0]} · {TOOL_META[n][1]}] {d}", "inputSchema": _schema(n),
                  "annotations": {"readOnlyHint": TOOL_META[n][0] == "READ", "destructiveHint": False}}
                 for n, (d, _) in TOOLS.items() if n in TOOL_META and tool_enabled(n, cfg)]
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tools}}
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
    """Real client handshake against a spawned server process: initialize → tools/list → tools/call(get_mcp_permissions)."""
    backend = Path(__file__).resolve().parents[1]
    reqs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "lifespan-selftest", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "get_mcp_permissions", "arguments": {}}}]
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
