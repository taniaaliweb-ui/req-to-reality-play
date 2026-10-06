"""Research acceptance pipeline (Phase 6.1).

Candidate Evidence → human Review → Accept as FACT / ESTIMATE / CONTEXT / ASSUMPTION (or REJECT)
  → structured Source → External/Manual evidence record (+ normalised life observation when the domain is a life-evidence domain)
  → Fact (FACT / ESTIMATE only) → provenance links stored on the candidate → Evidence-gap re-evaluation
  → replacement notices ("New evidence may replace assumption/prior X") — never applied silently.

The original candidate fields are never modified; reviewer-validated scope is stored separately (reviewed_scope).
Nothing here touches finalized snapshots: new evidence reaches a simulation only through a NEW snapshot version."""
from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.providers.base import Observation
from app.services import life_context as life
from app.services import truth
from app.services.repository import get_settings, now_iso

ACCEPT_AS = ("FACT", "ESTIMATE", "CONTEXT", "ASSUMPTION", "REJECT")
FACT_CATEGORY = {"income": "Economy", "employment_context": "Employment", "housing": "Housing", "education": "Education", "education_cost": "Education",
                 "migration": "Migration", "demographic": "Demographics", "mortality": "Demographics", "fertility": "Demographics",
                 "family_formation": "Social environment", "household_expenditure": "Economy", "retirement": "Economy", "pension": "Economy"}
DOMAIN_PRIORS = {"mortality": ["P-MORT-GOMPERTZ", "P-MORT-CHILD-5-14", "P-MORT-FALLBACK"],
                 "income": ["P-WAGE-NOMINAL-GROWTH", "P-WAGE-OCCUPATION", "P-WAGE-EXPERIENCE"],
                 "education": ["P-EDU-ENROL", "P-EDU-DROPOUT"], "education_cost": ["P-SPEND"], "housing": ["P-HOUSING"],
                 "household_expenditure": ["P-SPEND", "P-ECON-RULES"], "family_formation": ["P-REL-MEET", "P-REL-MARRY"],
                 "fertility": ["P-FERT-SHAPE", "P-FERT-FALLBACK"], "retirement": ["P-RET"], "pension": ["P-RET"], "migration": ["P-MIG-OPPORTUNITY"],
                 "employment_context": ["P-CAREER-FIRST-JOB", "P-CAREER-JOB-LOSS", "P-CAREER-REEMPLOY"]}
ASSUMPTION_DOMAINS = {"income": {"income", "wage"}, "housing": {"housing"}, "household_expenditure": {"household_expenditure", "spending"},
                      "education_cost": {"education_cost"}, "retirement": {"retirement"}, "pension": {"pension", "retirement"},
                      "family_formation": {"marriage", "family_formation"}, "fertility": {"fertility"}, "migration": {"migration"}}
SOURCE_TYPES = ("government", "World Bank", "UN", "OECD", "academic", "statistical agency", "newspaper", "historical archive", "industry", "other")


class AcceptanceError(ValueError):
    pass


def validate_scope(c: m.CandidateEvidence, form: dict) -> dict:
    """The reviewer must confirm scope. Missing scope blocks acceptance (it is never guessed)."""
    kind = form.get("acceptAs")
    if kind not in ACCEPT_AS:
        raise AcceptanceError("acceptAs must be one of " + ", ".join(ACCEPT_AS))
    if kind == "REJECT":
        return {"acceptAs": "REJECT"}
    errs = []
    country = life.iso3(form.get("country") or "")
    if not country:
        errs.append("country (ISO3) is required")
    ys, ye = form.get("yearStart"), form.get("yearEnd")
    if not isinstance(ys, int) or not isinstance(ye, int) or not (1800 <= ys <= ye <= 2100):
        errs.append("yearStart ≤ yearEnd (1800–2100) are required")
    pop = (form.get("population") or "").strip()
    if len(pop) < 3:
        errs.append("population scope is required (who the statistic describes)")
    src_title = (form.get("sourceTitle") or c.source or "").strip()
    src_org = (form.get("sourceOrganization") or "").strip()
    if len(src_org) < 2:
        errs.append("source organisation is required")
    value = (form.get("value") if form.get("value") is not None else c.value or "").strip()
    unit = (form.get("unit") if form.get("unit") is not None else c.unit or "").strip()
    domain = (form.get("domain") or "").strip()
    num = None
    if kind in ("FACT", "ESTIMATE"):
        try:
            num = Decimal(value.replace(",", ""))
        except InvalidOperation:
            errs.append("a numeric value is required for FACT / ESTIMATE (missing values are never estimated)")
        if not unit:
            errs.append("units are required for FACT / ESTIMATE")
        if not form.get("metric"):
            errs.append("metric name is required for FACT / ESTIMATE")
    if kind == "ASSUMPTION" and not form.get("lifeStage"):
        errs.append("lifeStage is required for an ASSUMPTION")
    if kind == "ASSUMPTION" and form.get("lifeStage") and form["lifeStage"] not in life.STAGE_LABEL:
        errs.append("unknown lifeStage")
    if domain and domain not in set(life.DATA_DOMAINS) | {"income"}:
        errs.append("domain must be one of " + ", ".join(life.DATA_DOMAINS + ["income"]))
    if form.get("sourceType") and form["sourceType"] not in SOURCE_TYPES:
        errs.append("sourceType must be one of " + ", ".join(SOURCE_TYPES))
    if errs:
        raise AcceptanceError("; ".join(errs))
    return {"acceptAs": kind, "country": country, "region": (form.get("region") or "").strip(), "yearStart": ys, "yearEnd": ye, "population": pop,
            "value": value, "numeric": None if num is None else str(num), "unit": unit, "domain": domain, "metric": (form.get("metric") or "").strip(),
            "sex": (form.get("sex") or "").upper() or None, "lifeStage": form.get("lifeStage"), "sourceTitle": src_title, "sourceOrganization": src_org,
            "sourceType": form.get("sourceType") or "other", "reliability": form.get("reliability") or "Moderate", "url": (form.get("url") or c.url or "").strip(),
            "publicationDate": form.get("publicationDate") or "", "confidence": form.get("confidence") or "medium", "note": form.get("note") or ""}


def review(db: Session, cid: str, form: dict) -> dict:
    c = db.get(m.CandidateEvidence, cid)
    if c is None:
        raise LookupError("Candidate not found")
    if c.status != "PENDING_REVIEW":
        raise AcceptanceError(f"Candidate already reviewed ({c.status})")
    scope = validate_scope(c, form)
    ts = now_iso()
    links: dict = {}
    if scope["acceptAs"] == "REJECT":
        c.status, c.accepted_as, c.review_note, c.reviewed_at, c.reviewed_scope, c.links = "REJECTED", "REJECT", form.get("note") or "", ts, scope, {}
        db.commit()
        return {"candidate": c, "replacements": [], "gapsReevaluated": False}
    eid = c.episode_id
    # 1. structured Source
    src = m.Source(id="SRC-" + uuid.uuid4().hex[:8], title=scope["sourceTitle"][:2000], organization=scope["sourceOrganization"][:300], url=scope["url"],
                   publication_date=scope["publicationDate"], accessed_date=ts[:10], geo_coverage=scope["country"] + (f" / {scope['region']}" if scope["region"] else ""),
                   time_coverage=f"{scope['yearStart']}–{scope['yearEnd']}", type=scope["sourceType"], reliability=scope["reliability"],
                   notes=f"Created from reviewed candidate evidence {c.id} (submitted by {c.submitted_by}).", created_at=ts, updated_at=ts)
    db.add(src)
    links["sourceId"] = src.id
    # 2. external / manual evidence record (raw, traceable) — numeric claims only
    if scope["numeric"] is not None:
        key_bits = [scope["domain"] or "research", scope["metric"], scope["country"], scope["region"], scope["sex"] or "", str(scope["yearStart"])]
        okey = "manual-research:" + ":".join(re.sub(r"[^A-Za-z0-9_.\-]", "_", b) for b in key_bits) + ":" + c.id
        obs = Observation(provider="manual-research", dataset="Reviewed research (human-accepted candidate evidence)",
                          indicator_code=f"{scope['domain'] or 'research'}.{scope['metric']}", indicator_name=scope["metric"], country_code=scope["country"],
                          country_name=scope["country"], year=scope["yearStart"], value=Decimal(scope["numeric"]), unit=scope["unit"],
                          source_organization=scope["sourceOrganization"], source_note=f"{scope['acceptAs']} accepted from {c.id}. Population: {scope['population']}",
                          source_url=scope["url"], raw={"candidateId": c.id, "scope": scope, "originalClaim": c.claim}, obs_key=okey[:160])
        truth.store_observations(db, [obs])
        db.flush()
        links["externalObservationId"] = obs.obs_key
        if scope["domain"] in life.DATA_DOMAINS:
            lo = life._upsert(db, "LO:" + obs.obs_key, external_observation_id=obs.obs_key, domain=scope["domain"], metric=scope["metric"],
                              metric_label=scope["metric"], value=scope["numeric"], unit=scope["unit"], country=scope["country"], region=scope["region"] or None,
                              geo_level="CITY" if scope["region"] else "NATIONAL", year=scope["yearStart"], sex=scope["sex"], population_scope=scope["population"],
                              observation_type="MANUAL", provider="manual-research", dataset=obs.dataset, source=scope["sourceTitle"],
                              source_organization=scope["sourceOrganization"], notes=f"{scope['acceptAs']} from candidate {c.id}; valid {scope['yearStart']}–{scope['yearEnd']}")
            links["lifeObservationId"] = lo.id
    # 3. Fact (only FACT / ESTIMATE; CONTEXT and ASSUMPTION are never Facts)
    if scope["acceptAs"] in ("FACT", "ESTIMATE") and eid:
        f = m.Fact(id="F-" + uuid.uuid4().hex[:8], episode_id=eid, category=FACT_CATEGORY.get(scope["domain"], "Social environment"),
                   metric=scope["metric"], value=scope["value"], unit=scope["unit"][:60], country=scope["country"], region=scope["region"],
                   year_start=scope["yearStart"], year_end=scope["yearEnd"], source_id=src.id, confidence=scope["confidence"], fact_type=scope["acceptAs"],
                   derived_from=None, notes=f"Accepted from candidate {c.id}. Population: {scope['population']}. {scope['note']}".strip(),
                   status="verified" if scope["acceptAs"] == "FACT" else "unverified", currency=None,
                   external_observation_id=links.get("externalObservationId"), provider="manual-research", dataset="Reviewed research",
                   indicator_code=f"{scope['domain'] or 'research'}.{scope['metric']}", is_prototype=False, created_at=ts, updated_at=ts)
        db.add(f)
        links["factId"] = f.id
    elif scope["acceptAs"] == "CONTEXT":
        cx = m.ContextEvidence(id="CTX-" + uuid.uuid4().hex[:8], topic=scope["domain"] or "research", country=scope["country"], region=scope["region"] or None,
                               year_start=scope["yearStart"], year_end=scope["yearEnd"], population_scope=scope["population"], claim=c.claim,
                               source=scope["sourceTitle"], source_url=scope["url"], evidence_type="QUALITATIVE" if scope["numeric"] is None else "MEASURABLE_CLAIM",
                               confidence=scope["confidence"].upper()[:10], notes=f"Accepted as CONTEXT from candidate {c.id}", created_at=ts, updated_at=ts)
        db.add(cx)
        links["contextId"] = cx.id
    elif scope["acceptAs"] == "ASSUMPTION" and eid:
        a = m.Assumption(id="ASM-" + uuid.uuid4().hex[:8], episode_id=eid, domain=scope["domain"] or "income", life_stage=scope["lifeStage"], claim=c.claim,
                         value=scope["value"], unit=scope["unit"], year_start=scope["yearStart"], year_end=scope["yearEnd"],
                         reason=f"Researched value accepted as an explicit ASSUMPTION from candidate {c.id} ({scope['sourceOrganization']})",
                         created_by="research-review", supporting_evidence=[x for x in (links.get("lifeObservationId"), src.id) if x],
                         confidence=scope["confidence"].upper()[:10], status="active", created_at=ts, updated_at=ts)
        db.add(a)
        links["assumptionId"] = a.id
    c.status, c.accepted_as, c.review_note, c.reviewed_at, c.reviewed_scope, c.links = "ACCEPTED", scope["acceptAs"], scope["note"], ts, scope, links
    db.commit()
    # 4. gap re-evaluation + replacement notices
    gaps = False
    if eid:
        life.detect_life_gaps(db, eid, list(get_settings(db).get("simulationRequiredDomains") or []))
        gaps = True
    reps = detect_replacements(db, c) if eid and scope["acceptAs"] in ("FACT", "ESTIMATE", "ASSUMPTION") else []
    return {"candidate": c, "replacements": reps, "gapsReevaluated": gaps}


def detect_replacements(db: Session, c: m.CandidateEvidence) -> list[m.EvidenceReplacement]:
    sc = c.reviewed_scope or {}
    dom, eid = sc.get("domain") or "", c.episode_id
    out: list[m.EvidenceReplacement] = []
    ts = now_iso()
    existing = {(r.target_kind, r.target_id) for r in db.scalars(select(m.EvidenceReplacement).where(m.EvidenceReplacement.candidate_id == c.id))}
    ys, ye = sc.get("yearStart"), sc.get("yearEnd")
    names = ASSUMPTION_DOMAINS.get(dom, {dom})
    for a in db.scalars(select(m.Assumption).where(m.Assumption.episode_id == eid, m.Assumption.status == "active")):
        if a.id == (c.links or {}).get("assumptionId") or a.domain not in names:
            continue
        if a.year_start is not None and a.year_end is not None and ys is not None and (a.year_end < ys or a.year_start > ye):
            continue
        if ("ASSUMPTION", a.id) in existing:
            continue
        out.append(m.EvidenceReplacement(id="REP-" + uuid.uuid4().hex[:8], episode_id=eid, candidate_id=c.id, target_kind="ASSUMPTION", target_id=a.id,
                                         message=f"New evidence may replace assumption {a.id} (\"{a.claim[:80]}\"): {c.id} — {sc.get('metric') or c.claim[:60]} "
                                                 f"{sc.get('value')} {sc.get('unit')} ({sc.get('country')} {ys}–{ye})."
                                                 + (" Income evidence feeds the simulation only once approved as a wage baseline (Employment Evidence); "
                                                    "retiring this assumption before that will block the rerun." if dom == "income" else ""), status="OPEN", created_at=ts))
    from app.simulation import priors as pri
    act = {p.key: p for p in pri.active(db)}
    for k in DOMAIN_PRIORS.get(dom, []):
        p = act.get(k)
        if p is None or ("PRIOR", p.id) in existing:
            continue
        out.append(m.EvidenceReplacement(id="REP-" + uuid.uuid4().hex[:8], episode_id=eid, candidate_id=c.id, target_kind="PRIOR", target_id=p.id,
                                         message=f"New evidence may replace prior {p.id} ({p.name}): {c.id} — {sc.get('metric') or c.claim[:60]} "
                                                 f"({sc.get('country')} {ys}–{ye}). Review the prior, then create a new snapshot and rerun.",
                                         status="OPEN", created_at=ts))
    db.add_all(out)
    db.commit()
    return out


def replacement_out(r: m.EvidenceReplacement) -> dict:
    return {"id": r.id, "episodeId": r.episode_id, "candidateId": r.candidate_id, "targetKind": r.target_kind, "targetId": r.target_id, "message": r.message,
            "status": r.status, "newSnapshotId": r.new_snapshot_id, "newRunId": r.new_run_id, "createdAt": r.created_at, "resolvedAt": r.resolved_at}


def replacement_snapshot(db: Session, rid: str, retire_assumption: bool = False) -> m.EvidenceReplacement:
    """Review replacement → create (and finalize) a NEW snapshot version. Old snapshots/simulations are untouched."""
    from app.services import snapshots as snaps
    from app.simulation.inputs import latest_final_snapshot
    r = db.get(m.EvidenceReplacement, rid)
    if r is None:
        raise LookupError("Replacement notice not found")
    if r.status not in ("OPEN",):
        raise AcceptanceError(f"Notice is {r.status}")
    if retire_assumption and r.target_kind == "ASSUMPTION":
        a = db.get(m.Assumption, r.target_id)
        if a is not None:
            a.status, a.updated_at = "retired", now_iso()
            db.commit()
    prev = latest_final_snapshot(db, r.episode_id)
    s = snaps.create(db, r.episode_id, prev.label if prev else "Evidence snapshot", notes=f"New version after reviewing {r.id}: {r.message[:300]}", parent=prev)
    snaps.finalize(db, s)
    r.status, r.new_snapshot_id = "SNAPSHOTTED", s.id
    db.commit()
    return r


def replacement_rerun(db: Session, rid: str) -> m.EvidenceReplacement:
    from app.simulation import inputs as sim_inputs
    from app.simulation import run as sim_run
    r = db.get(m.EvidenceReplacement, rid)
    if r is None:
        raise LookupError("Replacement notice not found")
    if r.status != "SNAPSHOTTED" or not r.new_snapshot_id:
        raise AcceptanceError("Create the new snapshot version first")
    canon = db.scalar(select(m.LifeSimulationRun).where(m.LifeSimulationRun.episode_id == r.episode_id, m.LifeSimulationRun.is_canonical.is_(True)))
    seed = canon.seed if canon else 20260101
    master = db.get(m.SimulationInput, canon.input_id).master_seed if canon else seed
    try:
        inp = sim_inputs.create(db, r.episode_id, r.new_snapshot_id, None, master, True, now_iso())
    except sim_inputs.InputError as e:
        raise AcceptanceError(str(e)) from e
    try:
        run = sim_run.run_life(db, inp.id, seed, label=f"rerun after {r.id} (new evidence)")
    except sim_run.RunError as e:
        raise AcceptanceError(str(e)) from e
    r.status, r.new_run_id, r.resolved_at = "RERUN", run.id, now_iso()
    db.commit()
    return r


def dismiss(db: Session, rid: str) -> m.EvidenceReplacement:
    r = db.get(m.EvidenceReplacement, rid)
    if r is None:
        raise LookupError("Replacement notice not found")
    r.status, r.resolved_at = "DISMISSED", now_iso()
    db.commit()
    return r
