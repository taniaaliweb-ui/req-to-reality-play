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
        factor = math.exp(z * sd - sd * sd / 2)  # rule:R-LOGNORMAL-MEAN
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
    ctx.events[-1]["lineage"] = {"kind": "WAGE_DERIVATION", "anchorCoverage": ref.get("anchorCoverage"),
                                 "chain": list(ref.get("chain") or []) + [{"step": "individual_position", "label": how, "factor": str(round(factor, 6)),
                                                                           "classification": "SIMULATED", "sourceIds": [ctx.pid("P-WAGE-SPREAD")]}],
                                 "referenceWage": str(round(ref["annual"], 2)), "currency": ref["currency"], "referenceClass": ref["class"]}


def step(ctx, st) -> None:
    emp, y, a = st["emp"], st["year"], st["age"]
    shock = st.get("shock") or {}
    if emp["state"] in ("child", "student"):
        if st["edu"]["state"] in ("completed", "dropout") and a >= ctx.P("P-CAREER-FIRST-JOB")["minAge"]:
            emp["state"] = "unemployed"
        else:
            lk = ctx.lock("first_job", y)
            if lk and a >= ctx.age_bound("lockedFirstJobMinAge"):
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
            ctx.tadd(pr, "firstJob")
            if shock.get("jobLoss"):
                pr.mult("verified historical shock (labour market)", 1 / shock["jobLoss"], "evidence")
            if ctx.decide(st, "career", "first_job", pr, rule="career.first_job", what="Finds a first job", importance=3,
                          before={"employment": "unemployed"}, after={"employment": "employee"}):
                _first_job(ctx, st)
            return
        pr = Prob(ctx.P("P-CAREER-REEMPLOY")["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual re-employment", prior_ids=[ctx.pid("P-CAREER-REEMPLOY")])
        ctx.tadd(pr, "reemploy")
        if shock.get("jobLoss"):
            pr.mult("verified historical shock (labour market)", 1 / shock["jobLoss"], "evidence")
        if ctx.decide(st, "career", "return_to_work", pr, rule="career.reemploy", what="Returns to work", importance=2,
                      before={"employment": "unemployed"}, after={"employment": "employee"}):
            emp.update(state="employee", unemployedYears=0, wageFactor=round(emp["wageFactor"] * ctx.sm("reemployWageFactor"), 6))
            emp["occupation"] = emp.get("occupation") or occupation_for(st)
        return
    emp["experience"] = emp.get("experience", 0) + 1
    B = ctx.P("P-CAREER-BUSINESS")
    if emp["state"] == "business_owner":
        biz = emp["business"]
        if not biz.get("success"):
            pr = Prob(B["successAnnual"], "PROVISIONAL_SYSTEM_PRIOR", "annual business breakthrough", prior_ids=[ctx.pid("P-CAREER-BUSINESS")]).mult("upward mobility control", ctx.ctl("upwardMobility"))
            ctx.tadd(pr, "businessSuccess")
            if ctx.decide(st, "career", "business_success", pr, rule="career.business", what="Business succeeds", importance=3):
                biz["success"] = True
                st["life"]["businessSuccess"] = 1
                st["pending"].append({"type": "business_revalue", "multiplier": str(ctx.sm("businessRevalueMultiplier"))})
                return
        pr = Prob(B["failAnnual"] * (ctx.sm("businessFailAfterSuccessFactor") if biz.get("success") else 1), "PROVISIONAL_SYSTEM_PRIOR", "annual business failure", prior_ids=[ctx.pid("P-CAREER-BUSINESS")])
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
    ctx.tadd(pr, "jobLoss").mult("downward risk control", ctx.ctl("downwardRisk")).mult("career volatility control", ctx.ctl("careerVolatility"))
    if shock.get("jobLoss"):
        pr.mult("verified historical shock (" + ", ".join(shock.get("eventIds", [])) + ")", shock["jobLoss"], "evidence")
    if ctx.decide(st, "career", "job_loss", pr, rule="career.job_loss", what="Loses job", importance=3,
                  before={"employment": emp["state"]}, after={"employment": "unemployed"}):
        emp["state"] = "unemployed"
        return
    # business start
    ov = ctx.override("starts_business", y)
    ref = ctx.any_ref_wage(st["country"], y)
    eligible = ctx.age_bound("businessMinAge") <= a <= ctx.age_bound("businessMaxAge") and ref is not None and liquid(st, st["currency"]) >= ref["annual"] * D(str(B["minSavingsYears"]))
    if ov and not st["life"]["businessAttempts"]:
        ctx.forced(st, "career", "business_start", "SCENARIO OVERRIDE: starts a business", rule="career.override", override=True,
                   before={"employment": emp["state"]}, after={"employment": "business_owner"})
        emp.update(state="business_owner", business={"startYear": y, "success": False})
        st["life"]["businessAttempts"] += 1
        st["pending"].append({"type": "business_capital", "share": str(B["capitalShare"])})
        return
    if eligible:
        pr = Prob(B["start"], "PROVISIONAL_SYSTEM_PRIOR", "annual business start (savings sufficient)", prior_ids=[ctx.pid("P-CAREER-BUSINESS")])
        ctx.tadd(pr, "businessStart").mult("career volatility control", ctx.ctl("careerVolatility"))
        if ctx.decide(st, "career", "business_start", pr, rule="career.business", what="Starts a business", importance=3, record_no=a % 5 == 0,  # rule:R-WHY-NOT-DISPLAY
                     
                      before={"employment": emp["state"]}, after={"employment": "business_owner"}):
            emp.update(state="business_owner", business={"startYear": y, "success": False})
            st["life"]["businessAttempts"] += 1
            st["pending"].append({"type": "business_capital", "share": str(B["capitalShare"])})
            return
    PR = ctx.P("P-CAREER-PROMOTION")
    if emp.get("seniority", 0) < PR["maxSeniority"]:
        pr = Prob(PR["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual promotion", prior_ids=[ctx.pid("P-CAREER-PROMOTION")])
        ctx.tadd(pr, "promotion").mult("upward mobility control", ctx.ctl("upwardMobility"))
        if ctx.decide(st, "career", "promotion", pr, rule="career.promotion", what=f"Promotion to seniority {emp.get('seniority', 0) + 1}", importance=2,
                      before={"seniority": emp.get("seniority", 0)}, after={"seniority": emp.get("seniority", 0) + 1}):
            emp["seniority"] = emp.get("seniority", 0) + 1
            return
    JC = ctx.P("P-CAREER-JOB-CHANGE")
    pr = Prob(JC["p"], "PROVISIONAL_SYSTEM_PRIOR", "annual voluntary job change", prior_ids=[ctx.pid("P-CAREER-JOB-CHANGE")]).mult("career volatility control", ctx.ctl("careerVolatility"))
    if ctx.decide(st, "career", "job_change", pr, rule="career.job_change", what="Changes job", importance=2):
        emp["wageFactor"] = round(emp["wageFactor"] * (1 + JC["raise"]), 6)
