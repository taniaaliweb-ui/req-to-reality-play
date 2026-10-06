"""Retirement: continued work → retirement (age-graded hazard, health, wealth) → optional return to work.
Pension rules are missing in the evidence: replacement comes from a retirement assumption (share) or prior P-RET (0 by default)."""
from __future__ import annotations

from app.simulation.context import D, q2
from app.simulation.probability import Prob


def _retire(ctx, st, e):
    R = ctx.P("P-RET")
    asm = ctx.assumption({"retirement", "pension"}, {"SHARE"}, st["year"])
    rate, src = (D(asm["parsed"]["value"]), f"assumption {asm['id']}") if asm else (D(str(R["replacement"])), f"prior {ctx.pid('P-RET')}")
    last = D(st.get("lastWage") or "0")
    st["ret"].update(state="retired", age=st["age"], pension=str(q2(last * rate)), pensionCurrency=st["currency"])
    st["emp"]["state"] = "retired"
    st["life"]["retirementAge"] = st["age"]
    e["explanation"] += f"\nPension: replacement {rate:.0%} of last wage ({src}) = {st['currency']} {q2(last * rate)}/yr."
    if asm:
        e["assumptionIds"].append(asm["id"])


def step(ctx, st) -> None:
    R = ctx.P("P-RET")
    a, y, emp = st["age"], st["year"], st["emp"]
    if emp["state"] == "retired":
        if a < ctx.age_bound("returnToWorkMaxAge") and st["health"] == "good":
            pr = Prob(R["returnToWork"], "PROVISIONAL_SYSTEM_PRIOR", "return to work after retirement", prior_ids=[ctx.pid("P-RET")])
            if ctx.decide(st, "retirement", "return_to_work", pr, rule="retirement.return", what="Returns to part-time work", importance=2):
                emp["state"] = "employee"
                st["ret"]["state"] = "partial"
        return
    if emp.get("firstJobYear") is None and emp["state"] not in ("unemployed", "inactive"):
        return
    lk = ctx.lock("retirement", y)
    if lk:
        _retire(ctx, st, ctx.forced(st, "retirement", "retirement", f"Retirement fixed by locked timeline event '{lk['title']}'", rule="retirement.locked", lock_id=lk["id"]))
        return
    ov = ctx.override("retires_early")
    if ov and a >= (ov.get("age") or R["earliest"]):
        _retire(ctx, st, ctx.forced(st, "retirement", "retirement", f"SCENARIO OVERRIDE: retires early at {a}", rule="retirement.override", override=True))
        return
    asm = ctx.assumption({"retirement"}, {"AGE"}, y)
    if asm and a >= int(float(asm["parsed"]["value"])):
        e = ctx.record(st, "retirement", "retirement", f"Retires at {a}: retirement-age assumption {asm['id']} ({asm['parsed']['value']}).",
                       rule="retirement.assumption", importance=3, cls="ASSUMPTION_BASED", assumption_ids=[asm["id"]])
        _retire(ctx, st, e)
        return
    if a < R["earliest"]:
        return
    if a >= ctx.age_bound("retirementCapAge"):
        _retire(ctx, st, ctx.record(st, "retirement", "retirement", f"Retires at model cap age {a} (prior P-AGE-BOUNDS.retirementCapAge).", rule="retirement.cap",
                                    importance=3, cls="PROVISIONAL_SYSTEM_PRIOR", prior_ids=[ctx.pid("P-RET")]))
        return
    sched = {int(k): v for k, v in R["hazard"].items()}
    base = sched[max(k for k in sched if k <= a)]
    pr = Prob(base, "PROVISIONAL_SYSTEM_PRIOR", f"retirement hazard at age {a}", prior_ids=[ctx.pid("P-RET")])
    if st["health"] in ("major_condition", "chronic_condition"):
        ctx.smod(pr, f"health {st['health']}", "retireMajorHealthAdd" if st["health"] == "major_condition" else "retireChronicHealthAdd", "add")
    if emp["state"] == "unemployed":
        ctx.smod(pr, "unemployed near retirement age", "retireUnemployedAdd", "add")
    if ctx.decide(st, "retirement", "retirement", pr, rule="retirement.hazard", what=f"Retires at {a}", importance=3,
                  before={"employment": emp["state"]}, after={"employment": "retired"}):
        _retire(ctx, st, ctx.events[-1])
