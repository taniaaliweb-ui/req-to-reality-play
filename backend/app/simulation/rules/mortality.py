"""Mortality: annual hazards (never 'death age = life expectancy').

PREFERRED — age-specific (method AGE_SPECIFIC_LIFE_TABLE, formula MORT-LT-ANNUAL v1):
  UN WPP abridged life table for the country, sex and nearest year (≤ P-MORT-LT.maxYearDistance):
    closed age group [x, x+n):  annual q = 1 − (1 − nqx)^(1/n)      (constant hazard within the group; n = 1 at age 0 → q0 itself)
    open group 100+:            annual q = 1 − exp(−mx)
BROAD FALLBACK — only when the snapshot has no life table for that country/sex/year (method BROAD_MEASURE_FALLBACK, MORT-BROAD v1):
  age 0 IMR/1000; ages 1–4 from Q5 and IMR; 5–14 factor × Q5; 15+ Gompertz with level from Q15–60 (slope prior).
PROVISIONAL FALLBACK — no evidence at all and P-MORT-FALLBACK enabled; else BLOCK.
Every hazard carries a lineage record: country, year, source year, sex, age, age group, source indicator, source value,
formula id/version and resulting annual probability."""
from __future__ import annotations

import math

from app.simulation.context import gompertz_A_from_q, gompertz_annual
from app.simulation.probability import Prob
from app.simulation.rules import SimulationBlocked

FORMULA_LT = ("MORT-LT-ANNUAL", "1")
FORMULA_BROAD = ("MORT-BROAD", "1")


def _lineage(method, country, year, sex, age, **kw) -> dict:
    return {"method": method, "country": country, "year": year, "sex": sex, "age": age, **kw}


def life_table_hazard(ctx, country: str, year: int, age: int, sex: str) -> Prob | None:
    sxk = sex if sex in ("MALE", "FEMALE") else "BOTH"
    tab = (ctx.ev.get("lifeTable") or {}).get(f"{country}|{sxk}")
    if not tab:
        return None
    best = min(tab, key=lambda y: (abs(int(y) - year), int(y)))
    if abs(int(best) - year) > ctx.P("P-MORT-LT")["maxYearDistance"]:
        return None
    groups = tab[best]
    starts = sorted(int(k) for k in groups)
    elig = [k for k in starts if k <= age]
    if not elig:
        return None
    g = max(elig)
    nxt = next((k for k in starts if k > g), None)
    cell = groups[str(g)]
    if "LT_QX" not in cell:
        return None
    qtxt, qid, typ, label = cell["LT_QX"]
    if nxt is None:
        if "LT_MX" not in cell:
            return None
        mtxt, mid, _t, _l = cell["LT_MX"]
        p = 1 - math.exp(-float(mtxt))
        ind, val, ids, formula, n = "LT_MX", mtxt, [mid], "annual q = 1 − exp(−mx) (open age group)", None
    else:
        n = nxt - g
        p = float(qtxt) if n == 1 else 1 - (1 - float(qtxt)) ** (1 / n)
        ind, val, ids = "LT_QX", qtxt, [qid]
        formula = "annual q = nqx (single-year group)" if n == 1 else f"annual q = 1 − (1 − nqx)^(1/n), n = {n}"
    proj = typ == "PROJECTION"
    cls = "EMPIRICAL" if n == 1 and not proj else "DERIVED_FROM_EMPIRICAL"
    lin = _lineage("AGE_SPECIFIC_LIFE_TABLE", country, year, sxk, age, sourceYear=int(best), ageGroup=label, ageGroupStart=g, ageGroupSpan=n,
                   sourceIndicator=f"UN WPP 2024 abridged life table {ind}", sourceValue=val, observationIds=ids, formula=formula,
                   formulaId=FORMULA_LT[0], formulaVersion=FORMULA_LT[1], annualProbability=round(p, 8), projection=proj, ageSpecificAvailable=True)
    pr = Prob(p, cls, f"UN WPP life table {ind} {label} = {float(val):.5f} ({country} {best}, {sxk.lower()}{', projection' if proj else ''}) → {formula}",
              evidence_ids=ids, prior_ids=[ctx.pid("P-MORT-LT")])
    pr.lineage = lin
    return pr


def broad_hazard(ctx, country: str, year: int, age: int, sex: str) -> Prob | None:
    g = ctx.P("P-MORT-GOMPERTZ")
    w = ctx.window("mortalityBroad")
    proj = lambda o: "DERIVED_FROM_EMPIRICAL" if o["type"] == "PROJECTION" else "EMPIRICAL"  # noqa: E731
    base = dict(formulaId=FORMULA_BROAD[0], formulaVersion=FORMULA_BROAD[1], ageSpecificAvailable=False)
    if age == 0:
        o = ctx.series("IMR", country, year, w)
        if o:
            p = o["value"] / 1000  # rule:R-PER-THOUSAND
            pr = Prob(p, proj(o), f"UN WPP infant mortality {o['value']:.1f}/1000 ({country} {o['year']})", evidence_ids=[o["id"]])
            pr.lineage = _lineage("BROAD_MEASURE_FALLBACK", country, year, sex, age, sourceYear=o["year"], ageGroup="0", sourceIndicator="UN WPP IMR",
                                  sourceValue=str(o["value"]), observationIds=[o["id"]], formula="q0 = IMR / 1000", annualProbability=round(p, 8), **base)
            return pr
    elif age <= 4:  # rule:R-UN-AGE-GROUPS
        q5, imr = ctx.series("Q5", country, year, w), ctx.series("IMR", country, year, w)
        if q5 and imr:
            q = max(0.0, (q5["value"] - imr["value"]) / (1000 - imr["value"]))  # rule:R-PER-THOUSAND
            p = 1 - (1 - q) ** 0.25  # rule:R-UN-AGE-GROUPS
            pr = Prob(p, "DERIVED_FROM_EMPIRICAL", f"ages 1–4 from UN WPP Q5 {q5['value']:.1f} and IMR {imr['value']:.1f} ({q5['year']})",
                      evidence_ids=[q5["id"], imr["id"]])
            pr.lineage = _lineage("BROAD_MEASURE_FALLBACK", country, year, sex, age, sourceYear=q5["year"], ageGroup="1-4", sourceIndicator="UN WPP Q5, IMR",
                                  sourceValue=f"{q5['value']}, {imr['value']}", observationIds=[q5["id"], imr["id"]],
                                  formula="4q1 = (Q5 − IMR)/(1000 − IMR); annual = 1 − (1 − 4q1)^(1/4)", annualProbability=round(p, 8), **base)
            return pr
    elif age <= 14:  # rule:R-UN-AGE-GROUPS
        q5 = ctx.series("Q5", country, year, w)
        if q5:
            f = ctx.P("P-MORT-CHILD-5-14")["factor"]
            p = f * q5["value"] / 1000  # rule:R-PER-THOUSAND
            pr = Prob(p, "DERIVED_FROM_EMPIRICAL", f"{f} × UN WPP Q5 {q5['value']:.1f}/1000 ({q5['year']})", evidence_ids=[q5["id"]], prior_ids=[ctx.pid("P-MORT-CHILD-5-14")])
            pr.lineage = _lineage("BROAD_MEASURE_FALLBACK", country, year, sex, age, sourceYear=q5["year"], ageGroup="5-14", sourceIndicator="UN WPP Q5",
                                  sourceValue=str(q5["value"]), observationIds=[q5["id"]], formula=f"annual = {f} × Q5/1000 (prior factor)", annualProbability=round(p, 8), **base)
            return pr
    else:
        s = "Female" if sex == "FEMALE" else "Male"
        o = ctx.series(f"Q1560{s}", country, year, w, sex if sex in ("MALE", "FEMALE") else "MALE")
        if o:
            A = gompertz_A_from_q(o["value"] / 1000, g["b"])  # rule:R-PER-THOUSAND
            p = min(g["maxAnnualHazard"], gompertz_annual(A, g["b"], age))
            pr = Prob(p, "DERIVED_FROM_EMPIRICAL", f"Gompertz hazard at age {age}: level from UN WPP {s.lower()} Q15–60 {o['value']:.1f}/1000 "
                      f"({country} {o['year']}), slope b={g['b']}", evidence_ids=[o["id"]], prior_ids=[ctx.pid("P-MORT-GOMPERTZ")])
            pr.lineage = _lineage("BROAD_MEASURE_FALLBACK", country, year, sex, age, sourceYear=o["year"], ageGroup="15-59 (broad)", sourceIndicator=f"UN WPP Q1560{s}",
                                  sourceValue=str(o["value"]), observationIds=[o["id"]],
                                  formula=f"Gompertz A·e^(b·x), A solved so 45q15 = Q15–60/1000, b = {g['b']} (prior); annual = 1 − exp(−∫hazard)",
                                  annualProbability=round(p, 8), **base)
            return pr
    return None


def hazard(ctx, country: str, year: int, age: int, sex: str) -> Prob:
    pr = life_table_hazard(ctx, country, year, age, sex) or broad_hazard(ctx, country, year, age, sex)
    if pr:
        return pr
    if not ctx.prior_enabled("P-MORT-FALLBACK"):
        raise SimulationBlocked(f"No mortality evidence for {country} {year} (age {age}) and fallback prior P-MORT-FALLBACK is disabled")
    g, fb = ctx.P("P-MORT-GOMPERTZ"), ctx.P("P-MORT-FALLBACK")
    h = fb["infant"] if age == 0 else fb["child"] if age < 15 else min(g["maxAnnualHazard"], gompertz_annual(fb["A"], fb["b"], age))  # rule:R-UN-AGE-GROUPS
    pr = Prob(h, "PROVISIONAL_SYSTEM_PRIOR", f"fallback mortality schedule (no evidence for {country} {year})", prior_ids=[ctx.pid("P-MORT-FALLBACK")])
    pr.lineage = _lineage("PROVISIONAL_FALLBACK", country, year, sex, age, sourceIndicator="none (prior P-MORT-FALLBACK)", sourceValue=None, observationIds=[],
                          formula="prior schedule", formulaId="MORT-FALLBACK", formulaVersion="1", annualProbability=round(h, 8), ageSpecificAvailable=False)
    return pr


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
    if a >= ctx.age_bound("healthModelMinAge") and ctx.prior_enabled("P-HEALTH-TRANSITIONS"):
        hm = ctx.P("P-HEALTH-TRANSITIONS")["hazardMultiplier"].get(st["health"], 1.0)
        pr.mult(f"health state {st['health']}", hm, "state")
        if hm != 1.0:
            pr.prior_ids.append(ctx.pid("P-HEALTH-TRANSITIONS"))
    st["lastHazard"] = round(pr.final(), 6)
    pr.lineage = {**(pr.lineage or {}), "modifiers": list(pr.modifiers), "finalAnnualProbability": round(pr.final(), 8)}
    st["mortality"] = pr.lineage
    return ctx.decide(st, "mortality", "death", pr, rule="mortality.annual_hazard", what=f"Death at age {a} ({st['country']} {y})", importance=3,
                      before={"alive": True}, after={"alive": False})
