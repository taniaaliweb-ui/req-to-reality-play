"""Explore Outcomes: distributions across many seeded runs from one frozen input.
These are model outcomes under the current evidence, assumptions and priors — NOT population forecasts."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from statistics import mean

DISCLAIMER = "Model outcomes under current evidence, assumptions and priors — not a population forecast and not the most likely real life."


def _stats(xs: list[float]) -> dict | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    q = lambda f: xs[min(len(xs) - 1, int(round(f * (len(xs) - 1))))]  # noqa: E731
    return {"n": len(xs), "min": xs[0], "p10": q(0.1), "p25": q(0.25), "median": q(0.5), "p75": q(0.75), "p90": q(0.9), "max": xs[-1], "mean": round(mean(xs), 2)}


def summarize(members: list[tuple[str, dict]]) -> dict:
    outs = [o for _, o in members]
    n = len(outs)
    groups = Counter(o["finalCurrency"] for o in outs)
    money = {}
    for key in ("lifetimeEarnings", "peakIncome", "peakNetWorth", "netWorthAtDeath"):
        per = {}
        for o in outs:
            for c, v in (o.get(key) or {}).items():
                per.setdefault(c, []).append(float(Decimal(v)))
        money[key] = {c: _stats(v) for c, v in per.items()}
    rate = lambda k: round(sum(1 for o in outs if o.get(k)) / n, 4) if n else None  # noqa: E731
    out = {"runs": n, "disclaimer": DISCLAIMER,
           "deathAge": _stats([o["deathAge"] for o in outs]), "yearsEmployed": _stats([o["yearsEmployed"] for o in outs]),
           "yearsUnemployed": _stats([o["yearsUnemployed"] for o in outs]), "retirementAge": _stats([o["retirementAge"] for o in outs]),
           "children": _stats([o["children"] for o in outs]), "money": money,
           "rates": {k: rate(k) for k in ("migrated", "homeOwner", "businessAttempt", "businessSuccess", "married", "divorced")},
           "finalCurrencies": dict(groups),
           "outliers": dict(Counter(f"{x['sign']}:{x['type']}" for o in outs for x in o.get("outliers") or []))}
    # representative runs within the largest final-currency group (comparable money)
    if n:
        cur = groups.most_common(1)[0][0]
        g = sorted([(rid, o) for rid, o in members if o["finalCurrency"] == cur], key=lambda x: float(Decimal((x[1]["netWorthAtDeath"] or {}).get(cur, "0"))))
        pick = lambda f: g[min(len(g) - 1, int(round(f * (len(g) - 1))))][0]  # noqa: E731
        da = [o["deathAge"] or 0 for _, o in members]
        mu = mean(da) if da else 0
        unusual = max(members, key=lambda x: len(x[1].get("outliers") or []) * 10 + abs((x[1]["deathAge"] or 0) - mu))[0]
        out["representative"] = {"currency": cur, "median": pick(0.5), "strong": pick(0.9), "weak": pick(0.1), "unusual": unusual,
                                 "note": f"Ranked by net worth at death in {cur} among the {len(g)} runs ending in that currency. "
                                         "'Median outcome' is the middle of the model distribution, not the most likely real life."}
    return out
