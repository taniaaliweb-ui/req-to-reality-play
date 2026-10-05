"""Education: not_started → primary → secondary → (tertiary | vocational) → completed, or dropout.
Entry probabilities come from World Bank gross enrollment ratios in the snapshot (DERIVED: a gross population
ratio converted to an individual probability, capped at 0.98; transitions use ratios of successive levels).
Fallback: P-EDU-ENROL. Household class, aptitude, ambition, discipline and finances modify."""
from __future__ import annotations

from app.simulation.probability import Prob

LEVEL_OCC = {"none": "elementary", "primary": "elementary", "secondary": "service", "vocational": "technician", "tertiary": "professional"}


def _ratio(ctx, st, level):
    return ctx.series("enrollment_rate", ctx.ch["country"] if not st["mig"]["abroad"] else st["country"], st["year"], 3, "", level)


def _entry(ctx, st, level: str) -> Prob:
    P = ctx.P("P-EDU-ENROL")
    if level == "PRIMARY":
        o = _ratio(ctx, st, "PRIMARY")
        if o:
            return Prob(min(0.98, o["value"] / 100), "DERIVED_FROM_EMPIRICAL", f"gross primary enrollment {o['value']:.1f}% ({o['year']}), capped 98%", evidence_ids=[o["id"]])
        return Prob(P["primary"], "PROVISIONAL_SYSTEM_PRIOR", "primary enrollment fallback", prior_ids=[ctx.pid("P-EDU-ENROL")])
    lo, hi = ("PRIMARY", "SECONDARY") if level == "SECONDARY" else ("SECONDARY", "TERTIARY")
    a, b = _ratio(ctx, st, lo), _ratio(ctx, st, hi)
    if a and b and a["value"] > 0:
        return Prob(min(0.98, b["value"] / a["value"]), "DERIVED_FROM_EMPIRICAL",
                    f"{hi.lower()} / {lo.lower()} gross enrollment {b['value']:.1f}% / {a['value']:.1f}% ({b['year']})", evidence_ids=[a["id"], b["id"]])
    k = "secondaryGivenPrimary" if level == "SECONDARY" else "tertiaryGivenSecondary"
    return Prob(P[k], "PROVISIONAL_SYSTEM_PRIOR", f"{level.lower()} transition fallback", prior_ids=[ctx.pid("P-EDU-ENROL")])


def _cls(ctx, pr: Prob) -> Prob:
    cm = ctx.P("P-EDU-ENROL")["classModifier"].get(ctx.ch.get("startingClass") or "", 0.0)
    if cm:
        pr.add(f"household class '{ctx.ch.get('startingClass')}'", cm, "prior")
        pr.prior_ids.append(ctx.pid("P-EDU-ENROL"))
    return pr


def _finish(st, level):
    st["edu"].update(state="completed", level=level, yearsInLevel=0)


def step(ctx, st) -> None:
    e = st["edu"]
    D = ctx.P("P-EDU-DURATION")
    a, y = st["age"], st["year"]
    if e["state"] == "not_started":
        if a < D["startAge"]:
            return
        pr = _cls(ctx, _entry(ctx, st, "PRIMARY")).add("aptitude", 0.08 * ctx.trait("aptitude"))
        if ctx.decide(st, "education", "enroll_primary", pr, rule="education.enroll", what="Enrolls in primary school", importance=2,
                      record_no=True, before={"education": "not_started"}, after={"education": "primary"}):
            e.update(state="primary", yearsInLevel=0)
        else:
            _finish(st, "none")
        return
    if e["state"] not in ("primary", "secondary", "tertiary", "vocational"):
        return
    lvl = e["state"]
    e["yearsInLevel"] += 1
    dur = D.get(lvl, ctx.P("P-EDU-VOCATIONAL")["years"])
    # university lock / override can pull the character forward
    lock_u = ctx.lock("university", y)
    if lvl != "tertiary" and lock_u:
        ctx.forced(st, "education", "enter_university", f"University fixed by locked timeline event '{lock_u['title']}'", rule="education.locked", lock_id=lock_u["id"],
                   before={"education": lvl}, after={"education": "tertiary"})
        e.update(state="tertiary", yearsInLevel=0, level="secondary")
        return
    if e["yearsInLevel"] < dur:
        if lvl == "vocational":
            return
        dp = ctx.P("P-EDU-DROPOUT")
        pr = Prob(dp[lvl], "PROVISIONAL_SYSTEM_PRIOR", f"annual {lvl} dropout", prior_ids=[ctx.pid("P-EDU-DROPOUT")]).add("discipline", -0.02 * ctx.trait("discipline"))
        if st["flags"].get("distress"):
            pr.mult("household financial distress", 1.5, "state")
        if ctx.decide(st, "education", "dropout", pr, rule="education.dropout", what=f"Leaves {lvl} education early", importance=2,
                      before={"education": lvl}, after={"education": "dropout"}):
            e.update(state="dropout", level={"primary": "none", "secondary": "primary", "tertiary": "secondary"}[lvl])
        return
    # level completed
    ctx.record(st, "education", f"complete_{lvl}", f"Completes {lvl} education ({dur} years, P-EDU-DURATION).", rule="education.complete",
               importance=2 if lvl != "primary" else 1, prior_ids=[ctx.pid("P-EDU-DURATION")], before={"education": lvl}, after={"level": lvl})
    if lvl == "primary":
        pr = _cls(ctx, _entry(ctx, st, "SECONDARY")).add("aptitude", 0.08 * ctx.trait("aptitude"))
        if ctx.decide(st, "education", "enter_secondary", pr, rule="education.transition", what="Continues to secondary school", importance=1, record_no=True):
            e.update(state="secondary", yearsInLevel=0, level="primary")
        else:
            _finish(st, "primary")
    elif lvl == "secondary":
        ov = ctx.override("attends_university")
        if ov:
            ctx.forced(st, "education", "enter_university", "SCENARIO OVERRIDE: attends university", rule="education.override", override=True)
            e.update(state="tertiary", yearsInLevel=0, level="secondary")
            return
        pr = _cls(ctx, _entry(ctx, st, "TERTIARY")).add("aptitude", 0.15 * ctx.trait("aptitude")).add("ambition", 0.06 * ctx.trait("ambition"))
        if st["flags"].get("distress"):
            pr.mult("household financial distress", 0.6, "state")
        if ctx.decide(st, "education", "enter_university", pr, rule="education.transition", what="Enters university", importance=3, record_no=True,
                      before={"education": "secondary"}, after={"education": "tertiary"}):
            e.update(state="tertiary", yearsInLevel=0, level="secondary")
            return
        v = ctx.P("P-EDU-VOCATIONAL")
        if ctx.decide(st, "education", "enter_vocational", Prob(v["p"], "PROVISIONAL_SYSTEM_PRIOR", "vocational track", prior_ids=[ctx.pid("P-EDU-VOCATIONAL")]),
                      rule="education.vocational", what="Takes vocational training", importance=2):
            e.update(state="vocational", yearsInLevel=0, level="secondary")
        else:
            _finish(st, "secondary")
    else:
        _finish(st, lvl)
