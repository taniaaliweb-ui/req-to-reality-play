"""Canonical deterministic audit rules (port of src/features/audit/rules.ts).
No AI. Historical/semantic audits are reported as not-yet-automated."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m


def run_audits(db: Session, episode_id: str) -> list[dict]:
    ep = db.get(m.Episode, episode_id)
    if ep is None:
        raise LookupError(episode_id)
    facts = list(db.scalars(select(m.Fact).where(m.Fact.episode_id == episode_id)))
    events = sorted(db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.episode_id == episode_id)), key=lambda e: e.year)
    econ = sorted(db.scalars(select(m.EconomicYear).where(m.EconomicYear.episode_id == episode_id)), key=lambda y: y.year)
    chapters = list(db.scalars(select(m.StoryChapter).where(m.StoryChapter.episode_id == episode_id)))
    sources = {x.id: x for x in db.scalars(select(m.Source))}
    out: list[dict] = []

    def push(category, outcome, title, explanation, refs=(), automated=True):
        out.append({"id": f"AU-{len(out) + 1}", "category": category, "outcome": outcome, "title": title,
                    "explanation": explanation, "refs": list(refs), "automated": automated})

    # Fact audit
    unsourced = [f for f in facts if f.fact_type in ("FACT", "ESTIMATE") and not f.source_id]
    if unsourced:
        push("Fact", "FAIL", f"{len(unsourced)} fact/estimate record(s) have no source", "Every FACT or ESTIMATE must reference a Source Registry entry.", [f.id for f in unsourced])
    else:
        push("Fact", "PASS", "All facts and estimates have sources", "Checked source_id on every FACT/ESTIMATE.")
    weak = [f for f in facts if f.source_id and f.source_id in sources and sources[f.source_id].reliability == "Weak"]
    if weak:
        push("Fact", "WARNING", f"{len(weak)} record(s) rely on a Weak source", "Corroborate with a stronger source.", [f.id for f in weak])
    dangling_src = [f for f in facts if f.source_id and f.source_id not in sources]
    if dangling_src:
        push("Fact", "FAIL", "Facts reference missing sources", "Malformed relationship: source_id does not exist.", [f.id for f in dangling_src])

    # Timeline audit
    born = ep.character.birth_year if ep.character else 0
    bad_age = [e for e in events if e.age != e.year - born]
    if bad_age:
        push("Timeline", "FAIL", "Age does not match birth year", "age must equal year − birth year.", [e.id for e in bad_age])
    else:
        push("Timeline", "PASS", "Ages consistent with birth year", "Checked all events.")
    death = next((e for e in events if e.title.lower() == "death"), None)
    after = [e for e in events if death and e.year > death.year]
    if after:
        push("Timeline", "FAIL", "Events occur after death", "No life events may follow death.", [e.id for e in after])
    first_job = next((e for e in events if e.category == "Career"), None)
    school = next((e for e in events if "secondary" in e.title.lower()), None)
    if first_job and school and first_job.year < school.year - 2:
        push("Timeline", "WARNING", "Career starts well before schooling ends", "Possible but should be justified.", [first_job.id, school.id])
    fact_ids = {f.id for f in facts}
    bad_refs = [e for e in events if any(fid not in fact_ids for fid in (e.fact_ids or []))]
    if bad_refs:
        push("Timeline", "WARNING", "Events reference unknown facts", "Malformed relationship: fact id not in ledger.", [e.id for e in bad_refs])

    # Economic audit (on prototype data)
    purchase = next((e for e in events if e.category == "Finance" and re.search("purchase", e.title, re.I)), None)
    if purchase:
        prior = next((y for y in econ if y.year == purchase.year - 1), None)
        if prior and prior.savings + prior.investments > 0:
            push("Economic", "WARNING", "Property purchase: verify down payment covered", f"Prior-year liquid assets exist; confirm ratio vs. price ({purchase.financial_effect}).", [purchase.id])
        else:
            push("Economic", "FAIL", "Property purchased with no prior savings", "House purchased despite insufficient assets.", [purchase.id])
    neg = [y for y in econ if y.savings < 0]
    if neg:
        push("Economic", "FAIL", "Negative savings detected", "Savings below zero without debt.", [y.id for y in neg])
    else:
        push("Economic", "PASS", "No negative savings", f"Checked {len(econ)} years.")
    if econ and econ[-1].assets + econ[-1].investments - econ[-1].liabilities < 0:
        push("Economic", "WARNING", "Dies with negative net worth", "Plausible but should be narratively addressed.")

    # Geographic
    mism = []
    for e in events:
        mt = re.search(r"moves to (\w+)", e.title, re.I)
        if e.category == "Migration" and mt and mt.group(1).lower() not in e.location.lower():
            mism.append(e.id)
    if mism:
        push("Geographic", "FAIL", "Migration destination ≠ event location", "Location field contradicts the title.", mism)
    else:
        push("Geographic", "PASS", "Migration locations consistent", "Checked relocation events.")

    # Assumptions
    unresolved = [f for f in facts if f.fact_type == "ASSUMPTION" and f.status != "verified"]
    if unresolved:
        push("Assumption", "WARNING", f"{len(unresolved)} unsupported assumption(s)", "Assumptions must be sourced, justified or removed.", [f.id for f in unresolved])

    # Story
    ids = {e.id for e in events}
    dangling = [c for c in chapters if any(i not in ids for i in (c.timeline_event_ids or []))]
    if dangling:
        push("Story", "FAIL", "Chapters reference deleted timeline events", "Story contradicts the timeline.", [c.id for c in dangling])
    else:
        push("Story", "PASS", "Chapter references resolve", "Semantic narrative-vs-timeline check requires the Audit Worker.")

    # Truth / economic-data audit (Phase 3)
    calcs = {c.output_fact_id: c for c in db.scalars(select(m.DerivedCalculation).where(m.DerivedCalculation.episode_id == episode_id)) if c.output_fact_id}
    inputs_by_calc: dict[str, list] = {}
    for ci in db.scalars(select(m.CalculationInput)):
        inputs_by_calc.setdefault(ci.calculation_id, []).append(ci)
    fact_by_id = {f.id: f for f in facts}
    no_lineage = [f for f in facts if f.fact_type == "DERIVED" and f.status == "verified" and f.id not in calcs and not f.is_prototype]
    if no_lineage:
        push("Economic", "FAIL", "Verified DERIVED value without calculation lineage", "A derived value can only be verified if its calculation and inputs are stored.", [f.id for f in no_lineage])
    verified_nosrc = [f for f in facts if f.fact_type in ("FACT", "ESTIMATE") and f.status == "verified" and not f.source_id]
    if verified_nosrc:
        push("Fact", "FAIL", "FACT marked verified but missing source", "Verification requires an identified source.", [f.id for f in verified_nosrc])
    proto_verified = [f for f in facts if f.is_prototype and f.status == "verified"]
    if proto_verified:
        push("Fact", "FAIL", f"{len(proto_verified)} PROTOTYPE figure(s) marked verified", "Demo values are not verified history. Replace them with sourced data or change their status.", [f.id for f in proto_verified])
    bad_infl, cross, fx_label, changed = [], [], [], []
    for fid, c in calcs.items():
        roles = {ci.role: fact_by_id.get(ci.fact_id) for ci in inputs_by_calc.get(c.id, [])}
        if c.calculation_type in ("inflation-adjust", "real-income"):
            if roles.get("source_cpi") is None or roles.get("target_cpi") is None:
                bad_infl.append(fid)
            elif roles["source_cpi"].country != roles["target_cpi"].country:
                cross.append(fid)
        if c.calculation_type == "currency-convert" and c.parameters_json.get("precision") != "annual-average":
            fx_label.append(fid)
        out_f = fact_by_id.get(fid)
        stored = (c.result_json or {}).get("result")
        if out_f is not None and stored is not None and out_f.value != stored:
            changed.append(fid)
    if bad_infl:
        push("Economic", "FAIL", "Inflation adjustment missing a CPI input", "Both source-year and target-year CPI must be stored as inputs.", bad_infl)
    if cross:
        push("Economic", "FAIL", "Cross-country CPI comparison", "CPI index levels from different countries cannot be compared directly.", cross)
    if fx_label:
        push("Economic", "WARNING", "FX conversion not labelled as annual average", "Annual-average rates must not be presented as exact daily rates.", fx_label)
    if changed:
        push("Economic", "FAIL", "Derived value edited after calculation", "The fact's value no longer matches its stored calculation result.", changed)
    if calcs and not (no_lineage or bad_infl or cross or changed):
        push("Economic", "PASS", f"{len(calcs)} derived value(s) have complete lineage", "Every saved calculation has its inputs, formula and engine version.")

    _labour_audits(db, episode_id, facts, push)

    push("Historical", "WARNING", "Historical consistency not yet verified", "Requires Audit Worker + dated event datasets (later phase).", automated=False)
    cultural = [f for f in facts if f.category == "Social environment" and f.fact_type == "ASSUMPTION"]
    push("Bias", "WARNING" if cultural else "PASS",
         "Cultural assumptions may encode stereotypes" if cultural else "No flagged cultural assumptions",
         "Social-environment assumptions require sourced justification. Full bias review needs human + Audit Worker.",
         [f.id for f in cultural])
    return out


def _labour_audits(db: Session, episode_id: str, facts: list, push) -> None:
    """Phase 4 labour-evidence rules (backend only: these records do not exist in local mode)."""
    from app.services import snapshots as snaps
    wage_re = re.compile(r"salary|wage|earning|income", re.I)
    bad_salary = [f.id for f in facts if f.fact_type == "FACT" and f.category in ("Employment", "Migration") and wage_re.search(f.metric or "")
                  and not f.external_observation_id and not f.is_prototype]
    if bad_salary:
        push("Fact", "FAIL", "Salary marked FACT without a matching wage observation", "A wage FACT must point at a stored source statistic; character salaries are ASSUMPTION or DERIVED.", bad_salary)
    fact_by_id = {f.id: f for f in facts}
    bls = list(db.scalars(select(m.EconomicBaseline).where(m.EconomicBaseline.episode_id == episode_id)))
    profiles = {p.id: p for p in db.scalars(select(m.CharacterEconomicProfile).where(m.CharacterEconomicProfile.episode_id == episode_id))}
    outside, net_bad, annual_bad, far, no_cpi, proto, unpinned, revised = [], [], [], [], [], [], [], []
    final_ids = {sb.economic_baseline_id for sb in db.scalars(select(m.SnapshotBaseline).join(m.EpisodeDatasetSnapshot, m.EpisodeDatasetSnapshot.id == m.SnapshotBaseline.snapshot_id)
                                                                .where(m.EpisodeDatasetSnapshot.status == "final"))}
    for b in bls:
        pr = profiles.get(b.profile_id)
        for ev in b.evidence or []:
            w = db.get(m.WageObservation, ev.get("wageObservationId"))
            if w is None:
                continue
            if pr and b.baseline_type != "ASSUMPTION" and ((pr.fields.get("employmentStatus") == "SELF_EMPLOYED" and w.employment_status == "EMPLOYEE")
                                                           or (pr.fields.get("country") and pr.fields["country"] != w.country)):
                outside.append(b.id)
            if ev.get("yearDistance", 0) > 3:
                far.append(b.id)
            o = db.get(m.ExternalObservation, ev.get("observationId"))
            if b.user_approved and o is not None and b.id not in final_ids and ev.get("observationUpdatedAt") and o.updated_at != ev["observationUpdatedAt"]:
                revised.append(b.id)
        if b.gross_or_net == "NET" and any((db.get(m.WageObservation, ev.get("wageObservationId")) or m.WageObservation(gross_or_net="UNKNOWN")).gross_or_net != "NET" for ev in b.evidence or []):
            net_bad.append(b.id)
        if b.pay_period != "ANNUAL" and b.annualization is not None and not b.annualization.get("method"):
            annual_bad.append(b.id)
        if b.pay_period == "ANNUAL" and any((ev.get("statisticType") and ev.get("payPeriod", "ANNUAL") != "ANNUAL") for ev in b.evidence or []) and not b.annualization:
            annual_bad.append(b.id)
        if b.baseline_type == "DERIVED" and not b.derived_calculation_ids:
            no_cpi.append(b.id)
        if b.baseline_type != "ASSUMPTION" and any(fact_by_id.get(fid) is not None and fact_by_id[fid].is_prototype for fid in b.source_fact_ids or []):
            proto.append(b.id)
        if b.user_approved and b.id not in final_ids:
            unpinned.append(b.id)
    def u(x):
        return sorted(set(x))
    if outside:
        push("Economic", "WARNING", "Wage evidence used outside its source population", "Evidence population (country / employee status) differs from the character without an explicit assumption.", u(outside))
    if net_bad:
        push("Economic", "FAIL", "Gross or unknown wage presented as take-home income", "LifeSpan does not compute net pay yet; never label gross/unknown earnings as net.", u(net_bad))
    if annual_bad:
        push("Economic", "FAIL", "Wage converted to annual without documented method", "Annualization must record its formula and explicit working-time assumptions.", u(annual_bad))
    if far:
        push("Economic", "WARNING", "Wage evidence year differs substantially from target", "Evidence more than 3 years away from the life stage it supports.", u(far))
    if no_cpi:
        push("Economic", "FAIL", "Derived inflation-adjusted wage missing CPI lineage", "A DERIVED baseline must reference its stored CPI calculations.", u(no_cpi))
    if proto:
        push("Economic", "FAIL", "Prototype income used as verified baseline", "PROTOTYPE figures cannot support a fact-supported or derived baseline.", u(proto))
    if revised:
        push("Economic", "FAIL", "Simulation-ready baseline references mutable, unpinned data", "Evidence changed after approval and the baseline is not pinned in a finalized snapshot.", u(revised))
    elif unpinned:
        push("Economic", "WARNING", "Approved baseline not yet pinned", "Finalize a dataset snapshot so future simulations use frozen evidence.", u(unpinned))
    tampered = []
    for s in db.scalars(select(m.EpisodeDatasetSnapshot).where(m.EpisodeDatasetSnapshot.episode_id == episode_id, m.EpisodeDatasetSnapshot.status == "final")):
        if s.content_hash and snaps.content_hash(db, s.id) != s.content_hash:
            tampered.append(s.id)
    if tampered:
        push("Economic", "FAIL", "Finalized dataset snapshot modified", "Snapshot contents no longer match the hash recorded when it was finalized.", tampered)
    if bls and not (outside or net_bad or annual_bad or no_cpi or proto or revised or tampered):
        push("Economic", "PASS", f"{len(bls)} economic baseline(s) pass labour-evidence rules", "Evidence, lineage and labelling checks passed.")
