"""Career: student → unemployed (seeking) → employee | self_employed | business_owner → retired; inactive on disability.
Events: first_job, job_change, promotion, job_loss, return_to_work, business_start, business_success, business_failure.
Income levels are NOT set here — wages come from evidence anchors in economics; this module only moves states
and draws the individual's SIMULATED position relative to the anchor at the first job."""
from __future__ import annotations

import math

from app.simulation.context import D
from app.simulation.probability import Prob
from app.simulation.rules import SimulationBlocked
from app.simulation.rules.education import LEVEL_OCC


def occupation_for(st) -> str:
    return LEVEL_OCC.get(st["edu"]["level"], "elementary")


def liquid(st, cur) -> D:
    a = st["acc"].get(cur) or {}
    return D(a.get("cash", "0")) + D(a.get("investments", "0"))


def _first_job(ctx, st, forced_lock=None):
    emp = st["emp"]
    occ = occupation_for(st)
    ref = ctx.ref_wage(st["country"], st["year"], occ)
    if ref is None:
        raise SimulationBlocked(f"No wage anchor or income assumption for {st['country']} — cannot model income in {st['year']}")
    r = ctx.rng(st["year"], "career:wage_position")
    sp = ctx.P("P-WAGE-SPREAD")
    if ref["low"] is not None and ref["high"] is not None and ref["annual"] > 0:
        u = r.random()
        factor = float((ref["low"] + (ref["high"] - ref["low"]) * D(str(u))) / ref["annual"])
        how = f"uniform position {u:.3f} within anchor range"
    else:
        z = r.gauss(0, 1)
        sd = sp["sd"] * ctx.ctl("randomness")
        factor = math.exp(z * sd - sd * sd / 2)
        how = f"log-normal individual factor (z={z:.3f}, sd={sd:.3f}, prior P-WAGE-SPREAD)"
    emp.update(state="employee", occupation=occ, wageFactor=round(factor, 6), firstJobYear=st["year"], seniority=0, unemployedYears=0)
    expl = (f"First job as {occ} worker in {st['country']}. Reference wage {ref['currency']} {ref['annual']:.0f}/yr [{ref['class']}] — {ref['method']} "
            f"(anchor {ref['anchorId']}). Individual position: {how} → factor {factor:.3f}. The resulting wage is SIMULATED, not factual.")
    if forced_lock:
        ctx.forced(st, "career", "first_job", f"First job fixed by locked timeline event '{forced_lock['title']}'. " + expl, rule="career.locked", lock_id=forced_lock["id"])
    else:
        ctx.events[-1]["explanation"] += "\n" + expl
        ctx.events[-1]["evidenceIds"] += ref["evidenceIds"]
        ctx.events[-1]["assumptionIds"] += ref["assumptionIds"]
        ctx.events[-1]["priorIds"] += ref["priorIds"] + [ctx.pid("P-WAGE-SPREAD")]


def step(ctx, st) -> None:
    emp, y, a = st["emp"], st["year"], st["age"]
    shock = st.get("shock") or {}
    if emp["state"] in ("child", "student"):
        if st["edu"]["state"] in ("completed", "dropout") and a >= ctx.P("P-CAREER-FIRST-JOB")["minAge"]:
            emp["state"] = "unemployed"
        else:
            lk = ctx.lock("first_job", y)
            if lk and a >= 12:
                st["edu"].update(state="completed")
                emp["state"] = "unemployed"
            else:
                return
    if emp["state"] == "retired":
        return
    # health interruption
    if st["health"] in ("disabled", "terminal") and emp["state"] in ("employee", "self_employed", "business_owner", "unemployed"):
        ctx.record(st, "career", "work_interruption", f"Stops working: health state {st['health']}.", rule="career.health", importance=3,
                   before={"employment": emp["state"]}, after={"employment": "inactive"}, prior_ids=[ctx.pid("P-HEALTH-TRANSITIONS")])
        emp["state"] = "inactive"
        return
    if emp["state"] == "inactive":
        if st["health"] not in ("disabled", "terminal"):
            emp["state"] = "unemployed"
        return
    if emp["state"] == "unemployed":
        emp["unemployedYears"] += 1
        lk = ctx.lock("first_job", y)
        if emp.get("firstJobYear") is None:
            if lk:
                _first_job(ctx, st, lk)
                return
            pr = Prob(ctx.P("P-CAREER-FIRST-JOB")["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual first-job finding", prior_ids=[ctx.pid("P-CAREER-FIRST-JOB")])
            pr.add("aptitude", 0.05 * ctx.trait("aptitude")).add("social skills", 0.05 * ctx.trait("socialSkills"))
            if shock.get("jobLoss"):
                pr.mult("verified historical shock (labour market)", 1 / shock["jobLoss"], "evidence")
            if ctx.decide(st, "career", "first_job", pr, rule="career.first_job", what="Finds a first job", importance=3,
                          before={"employment": "unemployed"}, after={"employment": "employee"}):
                _first_job(ctx, st)
            return
        pr = Prob(ctx.P("P-CAREER-REEMPLOY")["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual re-employment", prior_ids=[ctx.pid("P-CAREER-REEMPLOY")])
        pr.add("social skills", 0.08 * ctx.trait("socialSkills")).add("resilience", 0.06 * ctx.trait("resilience"))
        if shock.get("jobLoss"):
            pr.mult("verified historical shock (labour market)", 1 / shock["jobLoss"], "evidence")
        if ctx.decide(st, "career", "return_to_work", pr, rule="career.reemploy", what="Returns to work", importance=2,
                      before={"employment": "unemployed"}, after={"employment": "employee"}):
            emp.update(state="employee", unemployedYears=0, wageFactor=round(emp["wageFactor"] * 0.95, 6))
            emp["occupation"] = emp.get("occupation") or occupation_for(st)
        return
    emp["experience"] = emp.get("experience", 0) + 1
    B = ctx.P("P-CAREER-BUSINESS")
    if emp["state"] == "business_owner":
        biz = emp["business"]
        if not biz.get("success"):
            pr = Prob(B["successAnnual"], "PROVISIONAL_SYSTEM_PRIOR", "annual business breakthrough", prior_ids=[ctx.pid("P-CAREER-BUSINESS")]).mult("upward mobility control", ctx.ctl("upwardMobility"))
            pr.add("aptitude", 0.01 * ctx.trait("aptitude"))
            if ctx.decide(st, "career", "business_success", pr, rule="career.business", what="Business succeeds", importance=3):
                biz["success"] = True
                st["life"]["businessSuccess"] = 1
                st["pending"].append({"type": "business_revalue", "multiplier": "2"})
                return
        pr = Prob(B["failAnnual"] * (0.4 if biz.get("success") else 1), "PROVISIONAL_SYSTEM_PRIOR", "annual business failure", prior_ids=[ctx.pid("P-CAREER-BUSINESS")])
        pr.mult("downward risk control", ctx.ctl("downwardRisk")).mult("adversity control", ctx.ctl("adversity"))
        if shock.get("jobLoss"):
            pr.mult("verified historical shock", shock["jobLoss"], "evidence")
        if ctx.decide(st, "career", "business_failure", pr, rule="career.business", what="Business fails", importance=3,
                      before={"employment": "business_owner"}, after={"employment": "unemployed"}):
            emp.update(state="unemployed", business=None)
            st["pending"].append({"type": "business_writeoff"})
        return
    # employee / self_employed
    pr = Prob(ctx.P("P-CAREER-JOB-LOSS")["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual job loss", prior_ids=[ctx.pid("P-CAREER-JOB-LOSS")])
    pr.add("discipline", -0.012 * ctx.trait("discipline")).mult("downward risk control", ctx.ctl("downwardRisk")).mult("career volatility control", ctx.ctl("careerVolatility"))
    if shock.get("jobLoss"):
        pr.mult("verified historical shock (" + ", ".join(shock.get("eventIds", [])) + ")", shock["jobLoss"], "evidence")
    if ctx.decide(st, "career", "job_loss", pr, rule="career.job_loss", what="Loses job", importance=3,
                  before={"employment": emp["state"]}, after={"employment": "unemployed"}):
        emp["state"] = "unemployed"
        return
    # business start
    ov = ctx.override("starts_business", y)
    ref = ctx.any_ref_wage(st["country"], y)
    eligible = 25 <= a <= 60 and ref is not None and liquid(st, st["currency"]) >= ref["annual"] * D(str(B["minSavingsYears"]))
    if ov and not st["life"]["businessAttempts"]:
        ctx.forced(st, "career", "business_start", "SCENARIO OVERRIDE: starts a business", rule="career.override", override=True,
                   before={"employment": emp["state"]}, after={"employment": "business_owner"})
        emp.update(state="business_owner", business={"startYear": y, "success": False})
        st["life"]["businessAttempts"] += 1
        st["pending"].append({"type": "business_capital", "share": str(B["capitalShare"])})
        return
    if eligible:
        pr = Prob(B["start"], "PROVISIONAL_SYSTEM_PRIOR", "annual business start (savings sufficient)", prior_ids=[ctx.pid("P-CAREER-BUSINESS")])
        pr.add("risk tolerance", 0.012 * ctx.trait("riskTolerance")).add("ambition", 0.008 * ctx.trait("ambition")).mult("career volatility control", ctx.ctl("careerVolatility"))
        if ctx.decide(st, "career", "business_start", pr, rule="career.business", what="Starts a business", importance=3, record_no=a % 5 == 0,
                      before={"employment": emp["state"]}, after={"employment": "business_owner"}):
            emp.update(state="business_owner", business={"startYear": y, "success": False})
            st["life"]["businessAttempts"] += 1
            st["pending"].append({"type": "business_capital", "share": str(B["capitalShare"])})
            return
    PR = ctx.P("P-CAREER-PROMOTION")
    if emp.get("seniority", 0) < PR["maxSeniority"]:
        pr = Prob(PR["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual promotion", prior_ids=[ctx.pid("P-CAREER-PROMOTION")])
        pr.add("ambition", 0.04 * ctx.trait("ambition")).add("aptitude", 0.03 * ctx.trait("aptitude")).mult("upward mobility control", ctx.ctl("upwardMobility"))
        if ctx.decide(st, "career", "promotion", pr, rule="career.promotion", what=f"Promotion to seniority {emp.get('seniority', 0) + 1}", importance=2,
                      before={"seniority": emp.get("seniority", 0)}, after={"seniority": emp.get("seniority", 0) + 1}):
            emp["seniority"] = emp.get("seniority", 0) + 1
            return
    JC = ctx.P("P-CAREER-JOB-CHANGE")
    pr = Prob(JC["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual voluntary job change", prior_ids=[ctx.pid("P-CAREER-JOB-CHANGE")]).mult("career volatility control", ctx.ctl("careerVolatility"))
    if ctx.decide(st, "career", "job_change", pr, rule="career.job_change", what="Changes job", importance=2):
        emp["wageFactor"] = round(emp["wageFactor"] * (1 + JC["raise"]), 6)
