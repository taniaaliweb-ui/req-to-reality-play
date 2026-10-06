"""Rare positive/negative outcomes. Small base rates × outlier-intensity control; at most one per year.
Economic effects are applied by the accounting engine (gains/losses), so mobility emerges from the ledger."""
from __future__ import annotations

from app.simulation.probability import Prob


def step(ctx, st) -> None:
    O = ctx.P("P-OUTLIER")
    a = st["age"]
    if a < ctx.age_bound("adulthood"):
        return
    pid = ctx.pid("P-OUTLIER")
    inten = ctx.ctl("outlierIntensity")
    working = st["emp"]["state"] in ("employee", "self_employed", "business_owner")
    opts = [
        ("inheritance", O["inheritance"] if ctx.age_bound("inheritanceMinAge") <= a <= ctx.age_bound("inheritanceMaxAge") else 0, "positive", ctx.ctl("upwardMobility"), "Receives an inheritance"),
        ("investment_windfall", O["windfall"], "positive", ctx.ctl("upwardMobility"), "Investment / lottery-type windfall"),
        ("career_breakthrough", O["breakthrough"] if working else 0, "positive", ctx.ctl("upwardMobility"), "Career breakthrough"),
        ("major_asset_loss", O["assetLoss"] * (1 + (st.get("shock") or {}).get("assetLoss", 0) * ctx.er("assetLossShockScale")), "negative", ctx.ctl("adversity"), "Major asset loss (theft, fraud, disaster)"),
    ]
    for kind, base, sign, ctl, what in opts:
        if base <= 0:
            continue
        pr = Prob(base, "PROVISIONAL_SYSTEM_PRIOR", f"rare outcome: {kind.replace('_', ' ')}", prior_ids=[pid])
        pr.mult("outlier intensity control", inten).mult("upward mobility control" if sign == "positive" else "adversity control", ctl)
        if ctx.decide(st, "outliers", kind, pr, rule="outliers.annual", what=what, importance=3):
            st["life"]["outliers"].append({"year": st["year"], "type": kind, "sign": sign})
            if kind == "career_breakthrough":
                st["emp"]["wageFactor"] = round(st["emp"]["wageFactor"] * O["breakthroughMultiplier"], 6)
            else:
                st["pending"].append({"type": kind})
            return
