"""Relationships: not_present → partnered → married → separated → divorced; widowed via partner mortality.
Marriage is never forced (except by a locked timeline event). A partner is not assumed to work."""
from __future__ import annotations

from app.simulation.probability import Prob
from app.simulation.rules import mortality


def _new_partner(ctx, st, forced=False):
    r = ctx.rng(st["year"], "relationships:partner")
    W = ctx.P("P-REL-PARTNER-WORK")
    works = r.random() < W["p"]
    sex = "FEMALE" if ctx.ch["sex"] == "MALE" else "MALE"
    st["rel"].update(state="partnered", partner={"age": max(16, st["age"] + r.randint(-4, 3) * (1 if sex == "FEMALE" else -1)), "sex": sex, "works": works,
                                                  "incomeRatio": W["incomeRatio"] if works else 0, "alive": True, "metYear": st["year"]})
    return works


def step(ctx, st) -> None:
    rel, y, a = st["rel"], st["year"], st["age"]
    p = rel.get("partner")
    if p and p["alive"]:
        p["age"] += 1
        if rel["state"] in ("partnered", "married", "separated"):
            pr = mortality.hazard(ctx, st["country"], y, p["age"], p["sex"])
            if ctx.decide(st, "relationships", "widowhood", pr, rule="relationships.partner_mortality",
                          what=f"Partner dies at age {p['age']} (same mortality evidence as the character)", importance=3,
                          before={"relationship": rel["state"]}, after={"relationship": "widowed"}):
                p["alive"] = False
                rel["state"] = "widowed"
                return
    lk = ctx.lock("marriage", y)
    if lk and rel["state"] != "married":
        if rel["state"] != "partnered":
            _new_partner(ctx, st, True)
        ctx.forced(st, "relationships", "marriage", f"Marriage fixed by locked timeline event '{lk['title']}'", rule="relationships.locked", lock_id=lk["id"],
                   before={"relationship": rel["state"]}, after={"relationship": "married"})
        rel["state"] = "married"
        return
    M = ctx.P("P-REL-MEET")
    if rel["state"] in ("not_present", "divorced", "widowed") and M["minAge"] <= a <= 60:
        if ctx.override("no_marriage") and rel["state"] == "not_present" and not st["flags"].get("noMarriageNoted"):
            st["flags"]["noMarriageNoted"] = True
            ctx.forced(st, "relationships", "no_marriage", "SCENARIO OVERRIDE: does not marry (partnerships may still occur)", rule="relationships.override", override=True, importance=2)
        base = M["p"] * ((1 - M["declineRate"]) ** max(0, a - M["declineAfter"]))
        pr = Prob(base, "PROVISIONAL_SYSTEM_PRIOR", f"new partnership at age {a}", prior_ids=[ctx.pid("P-REL-MEET")])
        pr.add("social skills", 0.04 * ctx.trait("socialSkills")).mult("relationship volatility control", ctx.ctl("relationshipVolatility"))
        if ctx.decide(st, "relationships", "meet_partner", pr, rule="relationships.meet", what="Meets a partner", importance=2,
                      before={"relationship": rel["state"]}, after={"relationship": "partnered"}):
            works = _new_partner(ctx, st)
            ctx.events[-1]["explanation"] += f"\nPartner employment drawn from prior P-REL-PARTNER-WORK: {'works' if works else 'does not work for pay'}."
            ctx.events[-1]["priorIds"].append(ctx.pid("P-REL-PARTNER-WORK"))
        return
    if rel["state"] == "partnered":
        if ctx.override("no_marriage"):
            return
        asm = ctx.assumption({"marriage", "family_formation"}, {"SHARE"}, y)
        if asm:
            pr = Prob(float(asm["parsed"]["value"]), "ASSUMPTION_BASED", f"marriage probability from assumption {asm['id']}", assumption_ids=[asm["id"]])
        else:
            pr = Prob(ctx.P("P-REL-MARRY")["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual marriage while partnered", prior_ids=[ctx.pid("P-REL-MARRY")])
        if ctx.decide(st, "relationships", "marriage", pr, rule="relationships.marry", what="Marries", importance=3, record_no=True,
                      before={"relationship": "partnered"}, after={"relationship": "married"}):
            rel["state"] = "married"
        return
    S = ctx.P("P-REL-SEPARATE")
    if rel["state"] == "separated":
        pr = Prob(S["divorceGivenSeparation"], "PROVISIONAL_SYSTEM_PRIOR", "divorce after separation", prior_ids=[ctx.pid("P-REL-SEPARATE")])
        if ctx.decide(st, "relationships", "divorce", pr, rule="relationships.divorce", what="Divorce", importance=3,
                      before={"relationship": "separated"}, after={"relationship": "divorced"}):
            rel.update(state="divorced", partner=None)
        else:
            rel["state"] = "married"
            ctx.record(st, "relationships", "reconciliation", "Separation ends in reconciliation (divorce draw did not occur).", rule="relationships.divorce", importance=2)
        return
    if rel["state"] == "married":
        pr = Prob(S["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual separation", prior_ids=[ctx.pid("P-REL-SEPARATE")])
        pr.mult("relationship volatility control", ctx.ctl("relationshipVolatility")).mult("adversity control", ctx.ctl("adversity"))
        if st["flags"].get("distress"):
            pr.mult("household financial distress", 1.5, "state")
        if ctx.decide(st, "relationships", "separation", pr, rule="relationships.separate", what="Separation", importance=3,
                      before={"relationship": "married"}, after={"relationship": "separated"}):
            rel["state"] = "separated"
