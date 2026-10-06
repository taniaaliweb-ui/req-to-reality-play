"""Lightweight health state (not a medical model): good → minor/chronic/major → disabled/terminal.
Health feeds mortality (hazard multiplier), work interruption, healthcare spending and retirement."""
from __future__ import annotations

import math

from app.simulation.probability import Prob


def step(ctx, st) -> None:
    a = st["age"]
    if a < ctx.age_bound("healthModelMinAge") or not ctx.prior_enabled("P-HEALTH-TRANSITIONS"):
        return
    P = ctx.P("P-HEALTH-TRANSITIONS")
    pid = ctx.pid("P-HEALTH-TRANSITIONS")
    h = st["health"]
    ref = ctx.age_bound("healthReferenceAge")
    prog = ctx.sm("healthProgressionMultiplier")
    inten = ctx.ctl("healthIntensity") * ctx.ctl("adversity")

    def onset(base, label):
        return Prob(base, "PROVISIONAL_SYSTEM_PRIOR", label, prior_ids=[pid]).mult("health intensity × adversity controls", inten)

    def go(new, ev, pr, imp, what):
        if ctx.decide(st, "health", ev, pr, rule=f"health.{ev}", what=what, importance=imp, before={"health": h}, after={"health": new}):
            st["health"] = new
            return True
        return False

    if h == "good":
        if go("major_condition", "major_condition_onset", onset(P["majorBase"] * math.exp(P["majorSlope"] * (a - ref)), "major condition onset (age-graded)"), imp=3, what="Major health condition"):
            return
        if go("chronic_condition", "chronic_condition_onset", onset(P["chronicBase"] * math.exp(P["chronicSlope"] * (a - ref)), "chronic condition onset (age-graded)"), imp=2, what="Chronic condition"):
            return
        go("minor_condition", "minor_condition", onset(P["minorBase"], "minor condition"), imp=1, what="Minor health condition")
    elif h == "minor_condition":
        pr = ctx.tadd(Prob(P["recoverMinor"], "PROVISIONAL_SYSTEM_PRIOR", "recovery from minor condition", prior_ids=[pid]), "healthRecovery")
        if not go("good", "recovery", pr, imp=1, what="Recovery"):
            go("chronic_condition", "chronic_condition_onset", onset(P["chronicBase"] * prog * math.exp(P["chronicSlope"] * (a - ref)), "minor → chronic progression"), imp=2, what="Chronic condition")
    elif h == "chronic_condition":
        go("major_condition", "major_condition_onset", onset(P["majorBase"] * prog * math.exp(P["majorSlope"] * (a - ref)), "chronic → major progression"), imp=3, what="Major health condition")
    elif h == "major_condition":
        if go("terminal", "terminal_illness", onset(P["terminalFromMajor"], "major → terminal"), imp=3, what="Terminal illness"):
            return
        if go("disabled", "disability", onset(P["disabledFromMajor"], "major → disability"), imp=3, what="Disability"):
            return
        pr = ctx.tadd(Prob(P["recoverMajor"], "PROVISIONAL_SYSTEM_PRIOR", "recovery to chronic management", prior_ids=[pid]), "healthRecovery")
        go("chronic_condition", "partial_recovery", pr, imp=2, what="Partial recovery")
