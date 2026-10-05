"""Lightweight health state (not a medical model): good → minor/chronic/major → disabled/terminal.
Health feeds mortality (hazard multiplier), work interruption, healthcare spending and retirement."""
from __future__ import annotations

import math

from app.simulation.probability import Prob


def step(ctx, st) -> None:
    a = st["age"]
    if a < 15 or not ctx.prior_enabled("P-HEALTH-TRANSITIONS"):
        return
    P = ctx.P("P-HEALTH-TRANSITIONS")
    pid = ctx.pid("P-HEALTH-TRANSITIONS")
    h = st["health"]
    inten = ctx.ctl("healthIntensity") * ctx.ctl("adversity")

    def onset(base, label):
        return Prob(base, "PROVISIONAL_SYSTEM_PRIOR", label, prior_ids=[pid]).mult("health intensity × adversity controls", inten)

    def go(new, ev, pr, imp, what):
        if ctx.decide(st, "health", ev, pr, rule=f"health.{ev}", what=what, importance=imp, before={"health": h}, after={"health": new}):
            st["health"] = new
            return True
        return False

    if h == "good":
        if go("major_condition", "major_condition_onset", onset(P["majorBase"] * math.exp(P["majorSlope"] * (a - 30)), "major condition onset (age-graded)"), 3, "Major health condition"):
            return
        if go("chronic_condition", "chronic_condition_onset", onset(P["chronicBase"] * math.exp(P["chronicSlope"] * (a - 30)), "chronic condition onset (age-graded)"), 2, "Chronic condition"):
            return
        go("minor_condition", "minor_condition", onset(P["minorBase"], "minor condition"), 1, "Minor health condition")
    elif h == "minor_condition":
        pr = Prob(P["recoverMinor"], "PROVISIONAL_SYSTEM_PRIOR", "recovery from minor condition", prior_ids=[pid]).add("resilience", 0.1 * ctx.trait("resilience"))
        if not go("good", "recovery", pr, 1, "Recovery"):
            go("chronic_condition", "chronic_condition_onset", onset(P["chronicBase"] * 3 * math.exp(P["chronicSlope"] * (a - 30)), "minor → chronic progression"), 2, "Chronic condition")
    elif h == "chronic_condition":
        go("major_condition", "major_condition_onset", onset(P["majorBase"] * 3 * math.exp(P["majorSlope"] * (a - 30)), "chronic → major progression"), 3, "Major health condition")
    elif h == "major_condition":
        if go("terminal", "terminal_illness", onset(P["terminalFromMajor"], "major → terminal"), 3, "Terminal illness"):
            return
        if go("disabled", "disability", onset(P["disabledFromMajor"], "major → disability"), 3, "Disability"):
            return
        pr = Prob(P["recoverMajor"], "PROVISIONAL_SYSTEM_PRIOR", "recovery to chronic management", prior_ids=[pid]).add("resilience", 0.1 * ctx.trait("resilience"))
        go("chronic_condition", "partial_recovery", pr, 2, "Partial recovery")
