"""Mortality: annual hazards (never 'death age = life expectancy').
age 0      EMPIRICAL  — UN WPP infant mortality IMR/1000
ages 1–4   DERIVED    — q = (Q5−IMR)/(1000−IMR), annualised 1−(1−q)^(1/4)
ages 5–14  DERIVED    — factor(prior) × Q5/1000
ages 15+   DERIVED    — Gompertz A·e^(b·x); level A solved so that cumulative 15–60 mortality equals UN WPP Q1560 (sex-specific);
                        slope b is prior P-MORT-GOMPERTZ; capped at maxAnnualHazard; certain death at maxAge.
No evidence within ±2 years → PROVISIONAL fallback schedule (if enabled) else BLOCK."""
from __future__ import annotations

from app.simulation.context import gompertz_A_from_q, gompertz_annual
from app.simulation.probability import Prob
from app.simulation.rules import SimulationBlocked


def hazard(ctx, country: str, year: int, age: int, sex: str) -> Prob:
    g = ctx.P("P-MORT-GOMPERTZ")
    proj = lambda o: "DERIVED_FROM_EMPIRICAL" if o["type"] == "PROJECTION" else "EMPIRICAL"  # noqa: E731
    if age == 0:
        o = ctx.series("IMR", country, year, 2)
        if o:
            return Prob(o["value"] / 1000, proj(o), f"UN WPP infant mortality {o['value']:.1f}/1000 ({country} {o['year']})", evidence_ids=[o["id"]])
    elif age <= 4:
        q5, imr = ctx.series("Q5", country, year, 2), ctx.series("IMR", country, year, 2)
        if q5 and imr:
            q = max(0.0, (q5["value"] - imr["value"]) / (1000 - imr["value"]))
            return Prob(1 - (1 - q) ** 0.25, "DERIVED_FROM_EMPIRICAL", f"ages 1–4 from UN WPP Q5 {q5['value']:.1f} and IMR {imr['value']:.1f} ({q5['year']})",
                        evidence_ids=[q5["id"], imr["id"]])
    elif age <= 14:
        q5 = ctx.series("Q5", country, year, 2)
        if q5:
            f = ctx.P("P-MORT-CHILD-5-14")["factor"]
            return Prob(f * q5["value"] / 1000, "DERIVED_FROM_EMPIRICAL", f"{f} × UN WPP Q5 {q5['value']:.1f}/1000 ({q5['year']})",
                        evidence_ids=[q5["id"]], prior_ids=[ctx.pid("P-MORT-CHILD-5-14")])
    else:
        s = "Female" if sex == "FEMALE" else "Male"
        o = ctx.series(f"Q1560{s}", country, year, 2, sex if sex in ("MALE", "FEMALE") else "MALE")
        if o:
            A = gompertz_A_from_q(o["value"] / 1000, g["b"])
            h = min(g["maxAnnualHazard"], gompertz_annual(A, g["b"], age))
            return Prob(h, "DERIVED_FROM_EMPIRICAL", f"Gompertz hazard at age {age}: level from UN WPP {s.lower()} Q15–60 {o['value']:.1f}/1000 "
                        f"({country} {o['year']}), slope b={g['b']}", evidence_ids=[o["id"]], prior_ids=[ctx.pid("P-MORT-GOMPERTZ")])
    if not ctx.prior_enabled("P-MORT-FALLBACK"):
        raise SimulationBlocked(f"No mortality evidence for {country} {year} (age {age}) and fallback prior P-MORT-FALLBACK is disabled")
    fb = ctx.P("P-MORT-FALLBACK")
    h = fb["infant"] if age == 0 else fb["child"] if age < 15 else min(g["maxAnnualHazard"], gompertz_annual(fb["A"], fb["b"], age))
    return Prob(h, "PROVISIONAL_SYSTEM_PRIOR", f"fallback mortality schedule (no evidence for {country} {year})", prior_ids=[ctx.pid("P-MORT-FALLBACK")])


def step(ctx, st) -> bool:
    """Returns True when the character dies this year (evaluated at the end of the year)."""
    y, a = st["year"], st["age"]
    lk = ctx.lock("death", y)
    if lk:
        ctx.forced(st, "mortality", "death", f"Death in {y} fixed by locked timeline event '{lk['title']}'", rule="mortality.locked", lock_id=lk["id"])
        return True
    lly = ctx.last_lock_year()
    if lly is not None and y < lly:
        if not st["flags"].get("survivalNoted"):
            st["flags"]["survivalNoted"] = True
            ctx.record(st, "mortality", "survival_fixed", f"Survival through {lly} is fixed by locked timeline events; annual mortality draws start after {lly}.",
                       rule="mortality.locked_survival", importance=1)
        return False
    g = ctx.P("P-MORT-GOMPERTZ")
    if a >= g["maxAge"]:
        ctx.record(st, "mortality", "death", f"Model maximum age {g['maxAge']} reached (prior P-MORT-GOMPERTZ maxAge).", rule="mortality.max_age",
                   importance=3, prior_ids=[ctx.pid("P-MORT-GOMPERTZ")], cls="PROVISIONAL_SYSTEM_PRIOR")
        return True
    pr = hazard(ctx, st["country"], y, a, ctx.ch["sex"])
    if a >= 15 and ctx.prior_enabled("P-HEALTH-TRANSITIONS"):
        hm = ctx.P("P-HEALTH-TRANSITIONS")["hazardMultiplier"].get(st["health"], 1.0)
        pr.mult(f"health state {st['health']}", hm, "state")
        if hm != 1.0:
            pr.prior_ids.append(ctx.pid("P-HEALTH-TRANSITIONS"))
    st["lastHazard"] = round(pr.final(), 6)
    return ctx.decide(st, "mortality", "death", pr, rule="mortality.annual_hazard", what=f"Death at age {a} ({st['country']} {y})", importance=3,
                      before={"alive": True}, after={"alive": False})
