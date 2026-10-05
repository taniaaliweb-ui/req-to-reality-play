"""Children are simulated as events (never 'children = fertility rate').
Annual birth probability = TFR(country, year) / fertileYears × parityDecay^children (DERIVED from UN WPP TFR with a
timing-shape prior), × unpartneredFactor when not in a partnership; financial distress and family attachment modify."""
from __future__ import annotations

from app.simulation.probability import Prob


def step(ctx, st) -> None:
    y = st["year"]
    lk = ctx.lock("child", y)
    if lk:
        st["children"].append(y)
        ctx.forced(st, "fertility", "child_born", f"Child birth fixed by locked timeline event '{lk['title']}'", rule="fertility.locked", lock_id=lk["id"],
                   before={"children": len(st["children"]) - 1}, after={"children": len(st["children"])})
        return
    F = ctx.P("P-FERT-SHAPE")
    rel = st["rel"]
    partner = rel.get("partner") if rel["state"] in ("partnered", "married") else None
    mother_age = st["age"] if ctx.ch["sex"] == "FEMALE" else (partner["age"] if partner and partner.get("sex") == "FEMALE" else None)
    if mother_age is None or not (F["minAge"] <= mother_age <= F["maxAge"]):
        return
    o = ctx.series("TFR", st["country"], y, 2, "FEMALE", "") or ctx.series("TFR", st["country"], y, 2)
    if o:
        pr = Prob(o["value"] / F["fertileYears"], "DERIVED_FROM_EMPIRICAL", f"UN WPP TFR {o['value']:.2f} ({st['country']} {o['year']}) / {F['fertileYears']} fertile years",
                  evidence_ids=[o["id"]], prior_ids=[ctx.pid("P-FERT-SHAPE")])
    else:
        pr = Prob(ctx.P("P-FERT-FALLBACK")["annual"], "PROVISIONAL_SYSTEM_PRIOR", "fertility fallback (no TFR evidence)", prior_ids=[ctx.pid("P-FERT-FALLBACK")])
    n = len(st["children"])
    if n:
        pr.mult(f"parity decay ({n} existing children)", F["parityDecay"] ** n, "prior")
    if not partner:
        pr.mult("not in a partnership", F["unpartneredFactor"], "prior")
    if rel["state"] == "partnered":
        pr.mult("partnered but not married", 0.6, "prior")
    if st["flags"].get("distress"):
        pr.mult("household financial distress", 0.7, "state")
    pr.add("family attachment", 0.01 * ctx.trait("familyAttachment"))
    if ctx.decide(st, "fertility", "child_born", pr, rule="fertility.annual", what=f"Child born (child #{n + 1})", importance=3,
                  before={"children": n}, after={"children": n + 1}):
        st["children"].append(y)
