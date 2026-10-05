"""Builds the frozen SimulationInput from a FINALIZED dataset snapshot, explicit assumptions, locked
timeline events and the active prior registry — and the pre-simulation gate (Simulation Input Review).

Missing-data rule: an important dimension with no evidence must be covered by an explicit assumption
or an enabled provisional prior before it affects the simulation; otherwise the gate BLOCKS."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.services import economic_engine
from app.services.life_context import iso3
from app.simulation import ENGINE_VERSION
from app.simulation import priors as pri

CURRENCY_COUNTRY = {"AED": "ARE", "INR": "IND", "USD": "USA", "GBP": "GBR", "EUR": "EUU", "PKR": "PAK", "BDT": "BGD", "SAR": "SAU", "QAR": "QAT",
                    "KWD": "KWT", "OMR": "OMN", "BHD": "BHR", "NPR": "NPL", "LKR": "LKA", "PHP": "PHL"}
COUNTRY_CURRENCY = {v: k for k, v in CURRENCY_COUNTRY.items()}
DEFAULT_CONFIG = {"realism": 50, "randomness": 50, "adversity": 50, "upwardMobility": 50, "downwardRisk": 50, "careerVolatility": 50,
                  "relationshipVolatility": 50, "healthIntensity": 50, "outlierIntensity": 50}

# Simulation dimensions shown in the input review. critical = must be resolved before running.
DIMENSIONS = [
    ("mortality", "Mortality", True, ["P-MORT-GOMPERTZ", "P-MORT-CHILD-5-14", "P-MORT-FALLBACK"]),
    ("education", "Education", True, ["P-EDU-ENROL", "P-EDU-DROPOUT", "P-EDU-VOCATIONAL", "P-EDU-DURATION"]),
    ("income", "Income (wage anchors)", True, ["P-WAGE-NOMINAL-GROWTH", "P-WAGE-EXPERIENCE", "P-WAGE-SPREAD", "P-WAGE-OCCUPATION", "P-TAX-EFFECTIVE"]),
    ("career", "Career transitions", True, ["P-CAREER-FIRST-JOB", "P-CAREER-JOB-LOSS", "P-CAREER-REEMPLOY", "P-CAREER-PROMOTION", "P-CAREER-JOB-CHANGE", "P-CAREER-BUSINESS"]),
    ("marriage", "Marriage / relationships", True, ["P-REL-MEET", "P-REL-MARRY", "P-REL-SEPARATE", "P-REL-PARTNER-WORK"]),
    ("fertility", "Children", True, ["P-FERT-SHAPE", "P-FERT-FALLBACK"]),
    ("migration", "Migration", True, ["P-MIG-OPPORTUNITY"]),
    ("housing", "Housing", True, ["P-HOUSING"]),
    ("household_spending", "Household spending", True, ["P-SPEND", "P-FINANCE"]),
    ("health", "Health state", True, ["P-HEALTH-TRANSITIONS"]),
    ("retirement", "Retirement / pension", True, ["P-RET"]),
    ("outliers", "Rare outcomes", False, ["P-OUTLIER"]),
    ("historical", "Historical shocks", False, ["P-SHOCK-EFFECTS"]),
]
ASSUMPTION_DOMAIN = {"marriage": {"marriage", "family_formation", "relationships"}, "fertility": {"fertility"}, "migration": {"migration"},
                     "housing": {"housing"}, "household_spending": {"household_spending", "household_expenditure"}, "income": {"income"},
                     "retirement": {"retirement", "pension"}, "education": {"education", "education_cost"}, "mortality": {"mortality"},
                     "health": {"health", "mortality"}, "career": {"career", "employment"}, "outliers": set(), "historical": {"historical"}}


class InputError(ValueError):
    pass


def _num(v) -> Decimal | None:
    try:
        return Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def parse_assumption(a: dict) -> dict:
    """Machine-readable meaning of an assumption value. Unparseable assumptions stay as context only."""
    v, unit = _num(a.get("value")), (a.get("unit") or "").strip()
    u = unit.upper()
    if v is None:
        return {"kind": "TEXT"}
    if "%" in unit or "PERCENT" in u:
        return {"kind": "SHARE", "value": str(v / 100)}
    cur = next((c for c in re.findall(r"\b[A-Z]{3}\b", u) if c in CURRENCY_COUNTRY), None)
    if cur:
        per = "YEAR" if re.search(r"YEAR|ANNUAL|/Y\b|PA\b", u) else "MONTH"
        return {"kind": "AMOUNT", "value": str(v), "currency": cur, "period": per, "country": CURRENCY_COUNTRY[cur]}
    if "YEAR" in u and Decimal(10) <= v <= Decimal(100):
        return {"kind": "AGE", "value": str(v)}
    if Decimal(0) <= v <= Decimal(1) and ("PROB" in u or u == ""):
        return {"kind": "SHARE", "value": str(v)}
    return {"kind": "TEXT"}


def _lock_kind(e: m.TimelineEvent) -> str | None:
    t = e.title or ""
    if re.search(r"\b(died|death|passed away)\b", t, re.I):
        return "death"
    if e.category == "Migration":
        return "migration"
    if e.category == "Relationships" and re.search(r"marri|wedding", t, re.I):
        return "marriage"
    if e.category == "Family" and re.search(r"child|born|birth|son|daughter", t, re.I) and e.age > 12:
        return "child"
    if e.category == "Career" and re.search(r"retire", t, re.I):
        return "retirement"
    if e.category == "Career" and re.search(r"job|work|employ|hired", t, re.I):
        return "first_job"
    if e.category == "Education" and re.search(r"graduat|degree|university|college", t, re.I):
        return "university"
    return None


def _character(ch: m.Character) -> dict:
    return {"name": ch.name, "country": iso3(ch.country), "countryName": ch.country, "region": ch.region, "birthYear": ch.birth_year,
            "sex": "MALE" if (ch.gender or "").lower().startswith("m") else "FEMALE" if (ch.gender or "").lower().startswith("f") else "UNKNOWN",
            "settlement": ch.settlement, "startingClass": ch.starting_class, "family": ch.family, "traits": ch.traits}


def character_version(c: dict) -> str:
    return hashlib.sha256(json.dumps(c, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _evidence(db: Session, snap: m.EpisodeDatasetSnapshot) -> dict:
    series: dict[str, dict] = {}
    for r in db.scalars(select(m.SnapshotRecord).where(m.SnapshotRecord.snapshot_id == snap.id, m.SnapshotRecord.record_type == "life-observation")):
        p = r.payload
        if p.get("isPrototype"):
            continue
        v = _num(p.get("value"))
        if v is None:
            continue
        key = f"{p['metric']}|{p['country']}|{p.get('sex') or ''}|{p.get('educationLevel') or ''}"
        series.setdefault(key, {})[str(p["year"])] = [str(v), p["id"], p.get("observationType") or "ESTIMATE"]
    cpi: dict[str, dict] = {}
    fx: dict[str, dict] = {}
    for o in db.scalars(select(m.SnapshotObservation).where(m.SnapshotObservation.snapshot_id == snap.id)):
        p = o.payload
        c = iso3(p.get("countryCode") or "") or (p.get("countryCode") or "").upper()
        tgt = cpi if p.get("indicatorCode") == "FP.CPI.TOTL" else fx if p.get("indicatorCode") == "PA.NUS.FCRF" else None
        if tgt is not None and _num(o.value) is not None:
            tgt.setdefault(c, {})[str(p["year"])] = [str(_num(o.value)), o.external_observation_id]
    anchors = []
    for b in db.scalars(select(m.SnapshotBaseline).where(m.SnapshotBaseline.snapshot_id == snap.id)):
        p = b.payload
        if not p.get("userApproved"):
            continue
        cur = p.get("currency") or ""
        cov = p.get("temporalCoverage") or {}
        years = list(cov.get("directCoverage") or [])
        cls = "EMPIRICAL"
        if p.get("baselineType") == "ASSUMPTION":
            years, cls = list(range(p["yearStart"], p["yearEnd"] + 1)), "ASSUMPTION_BASED"
        elif p.get("baselineType") == "DERIVED":
            years = [y["year"] for y in cov.get("years") or [] if y.get("coverage") == "DERIVED"] or years
            cls = "DERIVED_FROM_EMPIRICAL"
        anchors.append({"id": p["id"], "kind": "BASELINE", "class": cls, "country": CURRENCY_COUNTRY.get(cur, ""), "currency": cur, "years": years,
                        "low": p.get("low"), "high": p.get("high"), "point": p.get("point"), "payPeriod": p.get("payPeriod") or "MONTH",
                        "grossOrNet": p.get("grossOrNet") or "UNKNOWN", "occupation": p.get("occupation") or "", "confidence": p.get("confidence"),
                        "factIds": p.get("sourceFactIds") or [], "evidenceIds": [a.get("observationId") for a in cov.get("anchors") or [] if a.get("observationId")]})
    recs = {}
    for r in db.scalars(select(m.SnapshotRecord).where(m.SnapshotRecord.snapshot_id == snap.id,
                                                       m.SnapshotRecord.record_type.in_(["assumption", "historical-event", "migration-path", "readiness", "policy"]))):
        recs.setdefault(r.record_type, []).append(r.payload)
    events = [{"id": e["id"], "name": e["name"], "category": e["category"], "geography": e.get("geography") or [], "start": e.get("startDate"),
               "end": e.get("endDate"), "verification": e.get("verification") or "unverified"} for e in recs.get("historical-event", [])]
    paths = [{"id": p["id"], "origin": p["origin"], "destination": p["destination"], "yearStart": p["yearStart"], "yearEnd": p["yearEnd"],
              "observationIds": p.get("observationIds") or []} for p in recs.get("migration-path", [])]
    return {"series": series, "cpi": cpi, "fx": fx, "wageAnchors": anchors, "events": events, "migrationPaths": paths,
            "snapshotAssumptions": recs.get("assumption", []), "readiness": (recs.get("readiness") or [None])[0]}


def latest_final_snapshot(db: Session, episode_id: str) -> m.EpisodeDatasetSnapshot | None:
    return db.scalar(select(m.EpisodeDatasetSnapshot).where(m.EpisodeDatasetSnapshot.episode_id == episode_id, m.EpisodeDatasetSnapshot.status == "final")
                     .order_by(m.EpisodeDatasetSnapshot.finalized_at.desc()))


def assemble(db: Session, episode_id: str, snapshot_id: str | None, config: dict | None, master_seed: int) -> dict:
    ep = db.get(m.Episode, episode_id)
    if ep is None or ep.character is None:
        raise LookupError("Episode not found")
    snap = db.get(m.EpisodeDatasetSnapshot, snapshot_id) if snapshot_id else latest_final_snapshot(db, episode_id)
    if snap is None or snap.episode_id != episode_id:
        raise InputError("A simulation needs a FINALIZED dataset snapshot. Create and finalize one in Dataset Snapshots first.")
    if snap.status != "final":
        raise InputError(f"Snapshot '{snap.label}' is a draft. Only finalized (immutable) snapshots can feed a simulation.")
    ch = _character(ep.character)
    cfg = {**DEFAULT_CONFIG, **(ep.character.controls or {}), **(config or {})}
    cfg = {k: max(0, min(100, int(cfg.get(k, 50)))) for k in DEFAULT_CONFIG}
    ev = _evidence(db, snap)
    # assumptions: only those frozen in the snapshot (the snapshot is the evidence of record)
    asm = [a | {"parsed": parse_assumption(a)} for a in ev.pop("snapshotAssumptions") if a.get("status", "active") == "active"]
    locks = []
    for e in db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.episode_id == episode_id, m.TimelineEvent.locked.is_(True)).order_by(m.TimelineEvent.year)):
        k = _lock_kind(e)
        locks.append({"id": e.id, "year": e.year, "age": e.age, "category": e.category, "title": e.title, "location": e.location, "kind": k,
                      "country": iso3(e.location) if k == "migration" else None, "city": (e.location or "").split(",")[0].strip()})
    act = [pri.prior_out(p) for p in pri.active(db)]
    payload = {"character": ch, "config": cfg, "assumptions": asm, "locks": locks, "priors": {p["key"]: p for p in act}, "evidence": ev,
               "snapshot": {"id": snap.id, "label": snap.label, "version": snap.version, "contentHash": snap.content_hash},
               "economicEngineVersion": getattr(economic_engine, "ENGINE_VERSION", getattr(economic_engine, "FORMULA_VERSION", "1")),
               "simulationEngineVersion": ENGINE_VERSION, "priorRegistryVersion": pri.registry_version(act)}
    payload["review"] = review(payload)
    return payload


def _years_with(series: dict, metric: str, country: str, years: range, window: int, sex: str = "", level: str = "") -> int:
    s = series.get(f"{metric}|{country}|{sex}|{level}") or {}
    have = {int(y) for y in s}
    return sum(1 for y in years if any(abs(y - h) <= window for h in have))


def review(p: dict) -> dict:
    """SIMULATION INPUT REVIEW: evidence status vs simulation status per dimension."""
    ch, ev, priors = p["character"], p["evidence"], p["priors"]
    b = ch["birthYear"]
    countries = [ch["country"]] + [l["country"] for l in p["locks"] if l["kind"] == "migration" and l["country"]] + [mp["destination"] for mp in ev["migrationPaths"]]
    countries = list(dict.fromkeys(c for c in countries if c))
    life = range(b, b + 91)
    sx = ch["sex"] if ch["sex"] in ("MALE", "FEMALE") else ""
    S = ev["series"]
    out = []
    blocked = []
    for key, label, critical, pkeys in DIMENSIONS:
        reasons: list[str] = []
        ev_ids_n = 0
        if key == "mortality":
            n = max((_years_with(S, f"Q1560{sx.title()}" if sx else "Q1560Male", c, life, 2) for c in countries), default=0)
            n2 = max((_years_with(S, "IMR", c, range(b, b + 1), 2) for c in countries), default=0)
            ev_ids_n = n + n2
            status = "VERIFIED" if n >= len(life) * 0.9 and n2 else "PARTIALLY VERIFIED" if ev_ids_n else "MISSING"
            reasons.append(f"UN WPP adult mortality (Q15–60) near {n}/{len(life)} life years; infant mortality {'present' if n2 else 'missing'} at birth. "
                           "Single-age hazards are DERIVED with a Gompertz-slope prior.")
        elif key == "education":
            n = sum(_years_with(S, "enrollment_rate", ch["country"], range(b + 6, b + 23), 3, "", lv) for lv in ("PRIMARY", "SECONDARY", "TERTIARY"))
            ev_ids_n = n
            status = "PARTIALLY VERIFIED" if n else "MISSING"
            reasons.append(f"Enrollment ratios (World Bank) near {n} school-age year/level combinations; costs not covered.")
        elif key == "income":
            per = []
            for c in countries:
                anc = [a for a in ev["wageAnchors"] if a["country"] == c] + [a for a in p["assumptions"] if a["domain"] in ASSUMPTION_DOMAIN["income"]
                                                                              and a["parsed"].get("kind") == "AMOUNT" and a["parsed"].get("country") == c]
                per.append((c, anc))
            missing = [c for c, anc in per if not anc]
            n_ev = sum(1 for c, anc in per for a in anc if a.get("kind") == "BASELINE" and a["class"] != "ASSUMPTION_BASED")
            ev_ids_n = n_ev
            status = "MISSING" if all(not a for _, a in per) else "PARTIALLY VERIFIED" if n_ev else "MISSING"
            for c, anc in per:
                reasons.append(f"{c}: " + (", ".join(f"{a['id']} ({'anchor years ' + ','.join(map(str, a['years'][:6])) if a.get('kind') == 'BASELINE' else 'assumption'})" for a in anc)
                                           if anc else "no approved wage baseline and no income assumption"))
            reasons.append("Other years are moved from the nearest anchor by CPI (DERIVED) or by the nominal-growth prior; never treated as observed.")
            if missing:
                blocked.append(f"Income for {', '.join(missing)}: add an approved wage baseline or an income assumption (amount + currency) and re-snapshot")
        elif key == "fertility":
            n = max((_years_with(S, "TFR", c, range(b + 18, b + 46), 2) for c in countries), default=0)
            ev_ids_n = n
            status = "PARTIALLY VERIFIED" if n else "MISSING"
            reasons.append(f"Total fertility rate near {n} of the fertile years — a population rate, converted to an individual annual hazard with a timing prior.")
        elif key == "migration":
            status = "PARTIALLY VERIFIED" if ev["migrationPaths"] else "MISSING"
            ev_ids_n = len(ev["migrationPaths"])
            reasons.append(f"{len(ev['migrationPaths'])} evidenced migration path(s); national migration figures are context, not individual probabilities.")
        elif key == "historical":
            ver = [e for e in ev["events"] if e["verification"] == "verified"]
            status = "VERIFIED" if ver else "MISSING"
            ev_ids_n = len(ver)
            reasons.append(f"{len(ver)} verified / {len(ev['events']) - len(ver)} unverified events (unverified events do not modify probabilities).")
        else:
            status = "MISSING"
            reasons.append("No usable evidence in the snapshot.")
        asm = [a for a in p["assumptions"] if a["domain"] in ASSUMPTION_DOMAIN[key]]
        usable_asm = [a for a in asm if a["parsed"]["kind"] != "TEXT"]
        enabled = [priors[k] for k in pkeys if k in priors and priors[k]["enabled"]]
        disabled = [k for k in pkeys if k in priors and not priors[k]["enabled"]]
        if status == "VERIFIED":
            sim = "VERIFIED"
        elif usable_asm and status == "MISSING":
            sim = "ASSUMPTION-COVERED"
        elif status == "PARTIALLY VERIFIED":
            sim = "PARTIALLY VERIFIED"
        elif enabled and key != "income":
            sim = "PRIOR-COVERED"
        else:
            sim = "BLOCKED"
        if key == "income" and any(b_.startswith("Income") for b_ in blocked):
            sim = "BLOCKED"
        if critical and sim == "BLOCKED" and key != "income":
            blocked.append(f"{label}: no evidence, no usable assumption and no enabled prior ({', '.join(disabled) or 'none'} disabled)")
        if disabled and status != "VERIFIED" and key != "income" and sim != "BLOCKED":
            reasons.append("Disabled priors: " + ", ".join(disabled))
        resolution = []
        resolution += [f"assumption {a['id']}" for a in usable_asm]
        resolution += [f"provisional prior {x['id']}" for x in enabled]
        out.append({"key": key, "label": label, "critical": critical, "evidenceStatus": status, "simulationStatus": sim, "evidenceCount": ev_ids_n,
                    "assumptionIds": [a["id"] for a in asm], "unusableAssumptionIds": [a["id"] for a in asm if a["parsed"]["kind"] == "TEXT"],
                    "priorIds": [x["id"] for x in enabled], "resolution": resolution, "reasons": reasons,
                    "needsAcknowledgement": critical and status != "VERIFIED"})
    return {"dimensions": out, "blocked": blocked, "canRun": not blocked,
            "needsAcknowledgement": [d["key"] for d in out if d["needsAcknowledgement"]],
            "priorLabel": pri.LABEL,
            "note": "Evidence coverage ≠ simulation coverage. ASSUMPTION-COVERED and PRIOR-COVERED dimensions are not research evidence."}


def _hash(payload: dict) -> str:
    core = {k: v for k, v in payload.items() if k not in ("review",)}
    core = json.loads(json.dumps(core, default=str))
    core["snapshot"] = {k: v for k, v in core["snapshot"].items() if k != "id"}
    return hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()


def create(db: Session, episode_id: str, snapshot_id: str | None, config: dict | None, master_seed: int, acknowledged: bool, ts: str) -> m.SimulationInput:
    payload = assemble(db, episode_id, snapshot_id, config, master_seed)
    rv = payload["review"]
    if not rv["canRun"]:
        raise InputError("BLOCKED — unresolved critical dimensions: " + "; ".join(rv["blocked"]))
    if rv["needsAcknowledgement"] and not acknowledged:
        raise InputError("Acknowledge the Simulation Input Review first: " + ", ".join(rv["needsAcknowledgement"]) + " rely on partial evidence, assumptions or provisional priors.")
    rec = m.SimulationInput(id="SIN-" + uuid.uuid4().hex[:10], episode_id=episode_id, dataset_snapshot_id=payload["snapshot"]["id"],
                            character_version=character_version(payload["character"]), assumption_ids=[a["id"] for a in payload["assumptions"]],
                            locked_timeline_event_ids=[l["id"] for l in payload["locks"]], prior_ids=[p["id"] for p in payload["priors"].values()],
                            prior_registry_version=payload["priorRegistryVersion"], economic_engine_version=str(payload["economicEngineVersion"]),
                            simulation_engine_version=ENGINE_VERSION, config=payload["config"], master_seed=master_seed, payload=payload,
                            review=rv, acknowledged=acknowledged, content_hash=_hash(payload), created_at=ts)
    db.add(rec)
    db.commit()
    return rec


def input_out(r: m.SimulationInput, full: bool = False) -> dict:
    out = {"id": r.id, "episodeId": r.episode_id, "datasetSnapshotId": r.dataset_snapshot_id, "snapshotLabel": r.payload["snapshot"]["label"],
           "characterVersion": r.character_version, "assumptionIds": r.assumption_ids, "lockedTimelineEventIds": r.locked_timeline_event_ids,
           "priorIds": r.prior_ids, "priorRegistryVersion": r.prior_registry_version, "economicEngineVersion": r.economic_engine_version,
           "simulationEngineVersion": r.simulation_engine_version, "config": r.config, "masterSeed": r.master_seed, "acknowledged": r.acknowledged,
           "contentHash": r.content_hash, "createdAt": r.created_at, "review": r.review, "immutable": True}
    if full:
        out["payload"] = r.payload
    return out
