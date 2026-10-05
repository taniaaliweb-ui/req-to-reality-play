"""Local export (JSON archive, CSV ledger, Markdown, printable HTML) and archive import as a NEW episode.
No paid PDF API: the HTML is printable with the browser's Print / Save as PDF."""
from __future__ import annotations

import csv
import html
import io
import re
import uuid

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services import snapshots as snap_svc
from app.services.repository import now_iso
from app.simulation import priors as pri

FORMAT, VERSION = "lifespan-episode-archive", 1
SNAP_CHILDREN = (m.SnapshotFact, m.SnapshotObservation, m.SnapshotBaseline, m.SnapshotRecord)


def _row(o) -> dict:
    return {c.key: getattr(o, c.key) for c in sa_inspect(o).mapper.column_attrs}


def _rows(db, model, *where) -> list[dict]:
    return [_row(x) for x in db.scalars(select(model).where(*where))]


def export_archive(db: Session, eid: str) -> dict:
    ep = db.get(m.Episode, eid)
    if ep is None:
        raise LookupError("Episode not found")
    snaps = list(db.scalars(select(m.EpisodeDatasetSnapshot).where(m.EpisodeDatasetSnapshot.episode_id == eid)))
    sids = [s.id for s in snaps]
    runs = list(db.scalars(select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == eid)))
    rids = [r.id for r in runs]
    facts = _rows(db, m.Fact, m.Fact.episode_id == eid)
    src_ids = {f["source_id"] for f in facts if f.get("source_id")}
    from app.simulation import run as sim_run
    can = sim_run.canonical(db, eid)
    receipt = None
    if can:
        from app.simulation import story as story_eng
        inp = db.get(m.SimulationInput, can.input_id)
        receipt = story_eng.receipt(inp.payload, sim_run.run_out(can), sim_run.load_states(db, can.id), sim_run.load_events(db, can.id))
    return {"format": FORMAT, "version": VERSION, "exportedAt": now_iso(), "episodeId": eid,
            "tables": {
                "episodes": [_row(ep)], "characters": _rows(db, m.Character, m.Character.episode_id == eid),
                "sources": [_row(s) for s in (db.get(m.Source, i) for i in sorted(src_ids)) if s is not None],
                "facts": facts, "timeline_events": _rows(db, m.TimelineEvent, m.TimelineEvent.episode_id == eid),
                "research_tasks": _rows(db, m.ResearchTask, m.ResearchTask.episode_id == eid),
                "story_chapters": _rows(db, m.StoryChapter, m.StoryChapter.episode_id == eid),
                "economic_years": _rows(db, m.EconomicYear, m.EconomicYear.episode_id == eid),
                "assumptions": _rows(db, m.Assumption, m.Assumption.episode_id == eid),
                "migration_paths": _rows(db, m.MigrationPath, m.MigrationPath.episode_id == eid),
                "episode_dataset_snapshots": [_row(s) for s in snaps],
                **{t.__tablename__: _rows(db, t, t.snapshot_id.in_(sids)) for t in SNAP_CHILDREN},
                "simulation_inputs": _rows(db, m.SimulationInput, m.SimulationInput.episode_id == eid),
                "life_simulation_runs": [_row(r) for r in runs],
                "annual_life_states": _rows(db, m.AnnualLifeState, m.AnnualLifeState.run_id.in_(rids)),
                "simulation_events": _rows(db, m.SimulationEvent, m.SimulationEvent.run_id.in_(rids)),
                "story_artifacts": _rows(db, m.StoryArtifact, m.StoryArtifact.episode_id == eid),
                "candidate_evidence": _rows(db, m.CandidateEvidence, m.CandidateEvidence.episode_id == eid),
            },
            "priorRegistry": [pri.prior_out(p) for p in db.scalars(select(m.SimulationPrior))],
            "lifeReceipt": receipt, "audits": {r.id: r.audit for r in runs},
            "note": "Portable LifeSpan episode archive. Simulated values remain SIMULATED; snapshots keep their frozen contents."}


ORDER = ["episodes", "characters", "facts", "timeline_events", "research_tasks", "story_chapters", "economic_years", "assumptions", "migration_paths",
         "episode_dataset_snapshots", "snapshot_facts", "snapshot_observations", "snapshot_baselines", "snapshot_records", "simulation_inputs",
         "life_simulation_runs", "annual_life_states", "simulation_events", "story_artifacts", "candidate_evidence"]
MODELS = {mdl.__tablename__: mdl for mdl in [m.Episode, m.Character, m.Fact, m.TimelineEvent, m.ResearchTask, m.StoryChapter, m.EconomicYear, m.Assumption,
                                             m.MigrationPath, m.EpisodeDatasetSnapshot, *SNAP_CHILDREN, m.SimulationInput, m.LifeSimulationRun,
                                             m.AnnualLifeState, m.SimulationEvent, m.StoryArtifact, m.CandidateEvidence]}
REMAP = ["episodes", "characters", "facts", "timeline_events", "research_tasks", "story_chapters", "economic_years", "assumptions", "migration_paths",
         "episode_dataset_snapshots", "simulation_inputs", "life_simulation_runs", "story_artifacts", "candidate_evidence"]


def import_archive(db: Session, data: dict) -> dict:
    import json
    if data.get("format") != FORMAT:
        raise ValueError("Not a LifeSpan episode archive")
    if data.get("version") != VERSION:
        raise ValueError(f"Unsupported archive version {data.get('version')} (this build reads version {VERSION})")
    T = data["tables"]
    prefix = "IMP" + uuid.uuid4().hex[:6] + "-"
    old = sorted({r["id"] for t in REMAP for r in T.get(t, []) if r.get("id")}, key=len, reverse=True)
    rx = re.compile("(?<![A-Za-z0-9_])(" + "|".join(re.escape(i) for i in old) + ")(?![A-Za-z0-9_])") if old else None
    doc = json.dumps(T)
    if rx:
        doc = rx.sub(lambda mm: prefix + mm.group(1), doc)
    T = json.loads(doc)
    new_eid = T["episodes"][0]["id"]
    T["episodes"][0]["title"] = T["episodes"][0]["title"] + " (imported)"
    for s in T.get("sources", []):
        if db.get(m.Source, s["id"]) is None:
            db.add(m.Source(**s))
    db.flush()
    final_snaps = []
    counts = {}
    for t in ORDER:
        mdl = MODELS[t]
        rows = T.get(t, [])
        fks = {c.name: list(c.foreign_keys)[0].column.table.name for c in mdl.__table__.columns if c.foreign_keys}
        for r in rows:
            if t == "episode_dataset_snapshots" and r.get("status") == "final":
                final_snaps.append((r["id"], r.get("content_hash"), r.get("finalized_at")))
                r = {**r, "status": "draft"}
            for col, tbl in fks.items():
                if r.get(col) and tbl in ("external_observations", "character_economic_profiles"):
                    tgt = {"external_observations": m.ExternalObservation, "character_economic_profiles": m.CharacterEconomicProfile}[tbl]
                    if db.get(tgt, r[col]) is None:
                        r = {**r, col: None}
            db.add(mdl(**r))
        db.flush()
        counts[t] = len(rows)
    hashes = []
    for sid, h, fin in final_snaps:
        s = db.get(m.EpisodeDatasetSnapshot, sid)
        new_h = snap_svc.content_hash(db, sid)
        s.status, s.content_hash, s.finalized_at = "final", new_h, fin
        hashes.append({"snapshotId": sid, "archivedHash": h, "recomputedHash": new_h})
    db.commit()
    return {"episodeId": new_eid, "idPrefix": prefix, "counts": counts, "snapshots": hashes,
            "note": "Imported as a separate episode; nothing existing was overwritten. Snapshot hashes are recomputed because record ids were re-keyed."}


# ----------------------------------------------------------------- flat exports
def ledger_csv(states: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    inc_keys = ["wages", "partnerWages", "pension", "interest", "windfalls", "familySupport"]
    exp_keys = ["tax", "housing", "food", "utilities", "transport", "other", "healthcare", "childCosts", "education", "remittancesSent", "debtInterest",
                "mortgageInterest", "migrationCost", "unaffordedConsumption"]
    w.writerow(["year", "age", "country", "currency", "employment", *inc_keys, "total_income", *exp_keys, "total_expenses", "net_worth", "reconciliation_difference", "label"])
    for s in states:
        e = s["economics"]
        w.writerow([s["year"], s["age"], s["country"], s["currency"], s["employment"], *[e["income"].get(k, "0") for k in inc_keys], e["totalIncome"],
                    *[e["expenses"].get(k, "0") for k in exp_keys], e["totalExpenses"], e["netWorth"].get(s["currency"], "0"),
                    (e["reconciliation"].get(s["currency"]) or {}).get("difference", "0"), "SIMULATED"])
    return buf.getvalue()


def markdown(title: str, story: dict | None, receipt: dict | None, script: str | None) -> str:
    out = [f"# {title}", "", "> All life events are SIMULATED. Factual context lines cite their sources.", ""]
    if receipt:
        out += ["## Life Receipt", ""] + [f"- **{k}**: {v}" for k, v in receipt.items() if k not in ("provenance", "label")] + ["", "### Provenance", ""] + \
               [f"- {k}: {v}" for k, v in receipt["provenance"].items() if k not in ("evidenceIds", "assumptionIds", "priorIds")] + [""]
    if story:
        out += ["## Story (structured local draft)", ""]
        for c in story["chapters"]:
            out += [f"### {c['number']}. {c['title']}", "", c["draft"], ""]
    if script:
        out += ["## Script", "", "```", script, "```", ""]
    return "\n".join(out)


def printable_html(title: str, story: dict | None, receipt: dict | None, script: str | None, appendix: dict | None) -> str:
    e = html.escape
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><title>{e(title)}</title><style>body{{font:14px/1.5 Georgia,serif;max-width:780px;margin:2rem auto;color:#111}}"
             "h1,h2,h3{font-family:Helvetica,Arial,sans-serif}.lbl{font:11px Helvetica;letter-spacing:.08em;text-transform:uppercase;color:#a33}"
             "table{border-collapse:collapse;width:100%}td{border-bottom:1px solid #ddd;padding:4px 6px;vertical-align:top}pre{white-space:pre-wrap}"
             "@media print{.noprint{display:none}}</style></head><body>",
             f"<p class='noprint'><button onclick='print()'>Print / Save as PDF</button></p><h1>{e(title)}</h1><p class='lbl'>Simulated life — not a real person's history</p>"]
    if receipt:
        parts.append("<h2>Life Receipt</h2><table>" + "".join(f"<tr><td>{e(str(k))}</td><td>{e(str(v))}</td></tr>" for k, v in receipt.items() if k != "provenance")
                     + "</table><h3>Provenance</h3><table>" + "".join(f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in receipt["provenance"].items()) + "</table>")
    if story:
        parts.append("<h2>Story</h2><p class='lbl'>" + e(story["label"]) + "</p>" + "".join(f"<h3>{c['number']}. {e(c['title'])}</h3><p>{e(c['draft'])}</p>" for c in story["chapters"]))
    if script:
        parts.append(f"<h2>Script</h2><pre>{e(script)}</pre>")
    if appendix:
        parts.append("<h2>Source Appendix</h2>" + "".join(f"<h3>{e(k)}</h3><ul>" + "".join(f"<li>{e(str(x))}</li>" for x in v[:200]) + "</ul>" for k, v in appendix.items()))
    parts.append("</body></html>")
    return "".join(parts)
