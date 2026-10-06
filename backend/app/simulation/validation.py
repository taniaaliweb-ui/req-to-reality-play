"""Model Validation report — makes the whole model inspectable before any external AI gets access."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services import economic_engine
from app.simulation import ENGINE_VERSION
from app.simulation import priors as pri
from app.simulation.model_registry import DETERMINISTIC_RULES, KNOWN_LIMITATIONS, METHODOLOGY, scan_constants

EMPIRICAL_INPUTS = [
    {"input": "LT_QX / LT_MX", "usedBy": "mortality (preferred)", "source": "UN WPP 2024 abridged life tables", "transformation": "MORT-LT-ANNUAL v1"},
    {"input": "IMR, Q5, Q1560Male/Female", "usedBy": "mortality (fallback only)", "source": "UN WPP 2024 demographic indicators", "transformation": "MORT-BROAD v1"},
    {"input": "TFR", "usedBy": "fertility", "source": "UN WPP 2024", "transformation": "TFR / fertileYears × parity decay (shape prior P-FERT-SHAPE)"},
    {"input": "enrollment_rate (primary/secondary/tertiary)", "usedBy": "education", "source": "World Bank WDI", "transformation": "ratio of successive levels, capped"},
    {"input": "FP.CPI.TOTL", "usedBy": "wage temporal adjustment", "source": "World Bank WDI", "transformation": "CPI ratio (DERIVED)"},
    {"input": "PA.NUS.FCRF", "usedBy": "currency conversion, migration wage ratio", "source": "World Bank WDI", "transformation": "annual average rate"},
    {"input": "approved wage baselines", "usedBy": "income anchors", "source": "ILOSTAT / imports (Phase 4)", "transformation": "anchor year only"},
    {"input": "migration paths", "usedBy": "migration", "source": "UN WPP net migration + timeline", "transformation": "path must exist; no probability taken from it"},
]


def _snapshot_inputs(db: Session, episode_id: str) -> dict | None:
    from app.simulation.inputs import _evidence, latest_final_snapshot
    snap = latest_final_snapshot(db, episode_id)
    if snap is None:
        return None
    ev = _evidence(db, snap)
    lt = ev.get("lifeTable") or {}
    fam = {}
    for k, ys in ev["series"].items():
        metric, country = k.split("|")[0], k.split("|")[1]
        fam.setdefault(metric, {}).setdefault(country, 0)
        fam[metric][country] += len(ys)
    return {"snapshot": {"id": snap.id, "label": snap.label, "contentHash": snap.content_hash},
            "lifeTable": {k: {"years": len(v), "first": min(int(y) for y in v), "last": max(int(y) for y in v)} for k, v in lt.items()},
            "series": fam, "cpiCountries": sorted(ev["cpi"]), "fxCountries": sorted(ev["fx"]), "wageAnchors": len(ev["wageAnchors"]),
            "assumptions": [{"id": a["id"], "domain": a.get("domain"), "claim": a.get("claim"), "value": a.get("value"), "unit": a.get("unit"),
                             "years": [a.get("yearStart"), a.get("yearEnd")], "classification": "USER_ASSUMPTION"}
                            for a in ev["snapshotAssumptions"] if a.get("status", "active") == "active"]}


def report(db: Session, episode_id: str | None = None) -> dict:
    act = [pri.prior_out(p) for p in pri.active(db)]
    by = {}
    for p in act:
        by.setdefault(p["classification"], []).append(p)
    scan = scan_constants()
    snap = _snapshot_inputs(db, episode_id) if episode_id else None
    canon = None
    if episode_id:
        r = db.scalar(select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == episode_id, m.LifeSimulationRun.is_canonical.is_(True)))
        if r is not None:
            states = db.scalars(select(m.AnnualLifeState).where(m.AnnualLifeState.run_id == r.id)).all()
            methods = {}
            for s in states:
                ml = (s.state.get("state") or {}).get("mortality") or {}
                if ml:
                    methods[ml.get("method")] = methods.get(ml.get("method"), 0) + 1
            canon = {"runId": r.id, "engineVersion": r.engine_version if hasattr(r, "engine_version") else None, "mortalityMethodYears": methods}
    return {
        "simulationEngineVersion": ENGINE_VERSION,
        "economicEngineVersion": getattr(economic_engine, "ENGINE_VERSION", getattr(economic_engine, "FORMULA_VERSION", "1")),
        "priorRegistryVersion": pri.registry_version(act),
        "classifications": pri.CLASSIFICATIONS,
        "activePriors": act,
        "priorsByClassification": {k: [p["key"] for p in v] for k, v in by.items()},
        "empiricalInputs": EMPIRICAL_INPUTS,
        "empiricalParameters": by.get("EMPIRICAL", []) + by.get("DERIVED", []),
        "assumptionParameters": (snap or {}).get("assumptions", []),
        "deterministicRules": [{"id": k, "description": v, "occurrences": [t for t in scan["tagged"] if t["rule"] == k]} for k, v in DETERMINISTIC_RULES.items()]
                              + [{"id": p["key"], "description": p["description"], "parameter": p["parameter"], "occurrences": []}
                                 for p in by.get("DETERMINISTIC_ACCOUNTING_RULE", [])],
        "methodology": METHODOLOGY,
        "knownLimitations": KNOWN_LIMITATIONS,
        "constantScan": {"unregistered": scan["unregistered"], "taggedCount": len(scan["tagged"]), "filesScanned": scan["filesScanned"],
                         "status": "PASS" if not scan["unregistered"] else "FAIL"},
        "episode": {"id": episode_id, "snapshotInputs": snap, "canonical": canon} if episode_id else None,
        "note": "Every probability or parameter not listed here as EMPIRICAL/DERIVED evidence or a USER_ASSUMPTION is a provisional model prior or a deterministic rule.",
    }
