"""Household economics + accounting (Decimal, cents).

METHODOLOGY (per currency c, per year):
    closing_NW(c) = opening_NW(c) + income(c) − expenses(c) + gains(c) + transfers_in(c) − transfers_out(c)
  NW = cash + investments + property + business − debt − mortgage.
  Income/expenses are flows in the residence currency (other currencies only receive interest / returns).
  Transfers that do not change NW (asset purchases, principal repayment, borrowing, selling investments,
  saving into investments) are internal moves between balance-sheet lines. Currency conversion at migration
  (only with FX evidence) is the only cross-currency transfer. Any non-zero residual is an audit failure.
Spending never lets a household run on impossible finances: shortfalls are covered in order by
  discretionary cuts → selling investments → family support (prior) → borrowing; persistent debt above the
  distress threshold triggers FINANCIAL DISTRESS and, after 3 years, a forced property sale."""
from __future__ import annotations

from decimal import Decimal

from app.simulation.context import D, q2
from app.simulation.probability import Prob

FIELDS = ("cash", "investments", "property", "business", "debt", "mortgage")
ZERO = Decimal("0.00")


def nw(a: dict) -> Decimal:
    return a["cash"] + a["investments"] + a["property"] + a["business"] - a["debt"] - a["mortgage"]


def _load(st) -> dict:
    return {c: {k: D(v.get(k, "0")) for k in FIELDS} for c, v in st["acc"].items()}


def _store(st, accs):
    st["acc"] = {c: {k: str(q2(v)) for k, v in a.items()} for c, a in accs.items()}


def household_size(st) -> int:
    kids = sum(1 for b in st["children"] if st["year"] - b < 22)
    partner = 1 if st["rel"]["state"] in ("partnered", "married") and (st["rel"].get("partner") or {}).get("alive") else 0
    return 1 + partner + kids


def wage(ctx, st) -> tuple[Decimal, dict | None]:
    emp = st["emp"]
    if emp["state"] not in ("employee", "self_employed", "business_owner"):
        return ZERO, None
    ref = ctx.ref_wage(st["country"], st["year"], emp.get("occupation") or "elementary")
    if ref is None:
        return ZERO, None
    X = ctx.P("P-WAGE-EXPERIENCE")
    expf = (D(1) + D(str(X["rate"]))) ** (min(emp.get("experience", 0), X["plateauYears"]) - X["anchorAverageExperience"]) if emp.get("experience", 0) < 200 else D(1)
    sen = (D(1) + D(str(ctx.P("P-CAREER-PROMOTION")["raise"]))) ** emp.get("seniority", 0)
    w = ref["annual"] * D(str(emp.get("wageFactor", 1))) * expf * sen
    B = ctx.P("P-CAREER-BUSINESS")
    if emp["state"] == "business_owner":
        w *= D(str(B["selfEmployedIncomeFactor"])) * (D(str(B["successIncomeMultiplier"])) if (emp.get("business") or {}).get("success") else D(1))
    if st["ret"].get("state") == "partial":
        w *= D("0.5")
    ref = {**ref, "priorIds": ref["priorIds"] + [ctx.pid("P-WAGE-EXPERIENCE"), ctx.pid("P-CAREER-PROMOTION")]}
    return q2(w), ref


def dependent(st) -> bool:
    """Before the first job, while living in the family home, the character is a dependant of the family of origin
    (outside this ledger): no own income or expenses are booked."""
    return st["emp"].get("firstJobYear") is None and st["emp"]["state"] in ("child", "student", "unemployed") and st["housing"] == "family_home"


def step(ctx, st) -> dict:
    y, cur = st["year"], st["currency"]
    if dependent(st):
        st["pending"] = [p for p in st["pending"] if p["type"] not in ("migration_cost",)]
        z = str(ZERO)
        return {"currency": cur, "dependent": True, "income": {"wages": z}, "expenses": {}, "gains": {}, "totalIncome": z, "totalExpenses": z, "netIncome": z,
                "balances": st["acc"], "netWorth": {c: str(q2(nw({k: D(v.get(k, "0")) for k in FIELDS}))) for c, v in st["acc"].items()},
                "reconciliation": {c: {"opening": "0.00", "income": z, "expenses": z, "gains": z, "transfers": z, "closing": "0.00", "difference": z} for c in st["acc"]},
                "shortfall": [], "notes": ["Dependant of the family of origin — household of origin not modelled in this ledger"], "householdSize": 1,
                "subsistenceFloor": z, "wageProvenance": None, "priorIds": [], "assumptionIds": [], "valueStatus": "SIMULATED"}
    accs = _load(st)
    for c in {cur} | {t["currency"] for t in st["transfers"]}:
        accs.setdefault(c, {k: ZERO for k in FIELDS})
    opening = {c: nw(a) for c, a in accs.items()}
    # transfers recorded earlier this year (currency conversion at migration) were already applied to balances
    tr = {c: ZERO for c in accs}
    for t in st["transfers"]:
        tr[t["currency"]] += D(t["amount"])
        opening[t["currency"]] -= D(t["amount"])  # opening is before the conversion
    st["transfers"] = []
    S, FN, H = ctx.P("P-SPEND"), ctx.P("P-FINANCE"), ctx.P("P-HOUSING")
    prior_used = {ctx.pid("P-SPEND"), ctx.pid("P-FINANCE")}
    asm_used: set[str] = set()
    inc: dict[str, Decimal] = {}
    exp: dict[str, Decimal] = {}
    gains: dict[str, dict[str, Decimal]] = {c: {} for c in accs}
    other_inc: dict[str, dict[str, Decimal]] = {c: {} for c in accs}
    # ---------------- income
    w, ref = wage(ctx, st)
    inc["wages"] = w
    if w > 0:
        st["lastWage"] = str(w)
    p = st["rel"].get("partner") or {}
    inc["partnerWages"] = ZERO
    if st["rel"]["state"] in ("partnered", "married") and p.get("alive") and p.get("works") and p.get("age", 0) < 62:
        pref = ctx.ref_wage(st["country"], y, "service")
        if pref:
            inc["partnerWages"] = q2(pref["annual"] * D(str(p["incomeRatio"])))
            prior_used.add(ctx.pid("P-REL-PARTNER-WORK"))
    inc["pension"] = q2(D(st["ret"].get("pension") or "0")) if st["ret"].get("state") == "retired" and st["ret"].get("pensionCurrency") == cur else ZERO
    ref_all = ctx.any_ref_wage(st["country"], y)
    ref_annual = ref_all["annual"] if ref_all else (w or D(1))
    O = ctx.P("P-OUTLIER")
    windfall = ZERO
    for pe in st["pending"]:
        if pe["type"] == "inheritance":
            windfall += q2(ref_annual * D(str(O["inheritanceYears"])))
        elif pe["type"] == "investment_windfall":
            windfall += q2(ref_annual * D(str(O["windfallYears"])))
    inc["windfalls"] = windfall
    for c, a in accs.items():
        if a["cash"] > 0:
            v = q2(a["cash"] * D(str(FN["cashRate"])))
            if c == cur:
                inc["interest"] = v
            else:
                other_inc[c]["interest"] = v
    inc.setdefault("interest", ZERO)
    hh_income = inc["wages"] + inc["partnerWages"] + inc["pension"]
    st["lastHouseholdIncome"] = str(hh_income)
    n = household_size(st)
    equiv = D(1) + D("0.5") * (n - 1)
    floor = q2(ref_annual * D(str(S["floorOfReferenceWage"])) * equiv)
    base = max(hh_income, floor)
    # ---------------- expenses
    tax_p = ctx.P("P-TAX-EFFECTIVE")
    rate = D(str(tax_p["byCountry"].get(st["country"], tax_p["default"])))
    gross_net = (ref or {}).get("grossOrNet", "UNKNOWN")
    exp["tax"] = q2((inc["wages"] + inc["partnerWages"]) * rate) if gross_net != "NET" else ZERO
    prior_used.add(ctx.pid("P-TAX-EFFECTIVE"))
    ha = ctx.assumption({"housing"}, {"AMOUNT", "SHARE"}, y, st["country"])
    hs = st["housing"]
    if ha and hs not in ("family_home", "owned", "mortgaged"):
        pa = ha["parsed"]
        exp["housing"] = q2(D(pa["value"]) * (D(12) if pa.get("period") == "MONTH" else D(1))) if pa["kind"] == "AMOUNT" else q2(base * D(pa["value"]))
        asm_used.add(ha["id"])
    else:
        exp["housing"] = q2(base * D(str(H["costShare"].get(hs, 0))))
        prior_used.add(ctx.pid("P-HOUSING"))
    sa = ctx.assumption({"household_spending", "household_expenditure"}, {"AMOUNT", "SHARE"}, y, st["country"])
    fd = ctx.trait("financialDiscipline")
    if sa:
        pa = sa["parsed"]
        total = q2(D(pa["value"]) * (D(12) if pa.get("period") == "MONTH" else D(1))) if pa["kind"] == "AMOUNT" else q2(base * D(pa["value"]))
        exp["food"], exp["utilities"], exp["transport"], exp["other"] = q2(total * D("0.45")), q2(total * D("0.12")), q2(total * D("0.13")), q2(total * D("0.30"))
        asm_used.add(sa["id"])
    else:
        exp["food"] = q2(base * D(str(S["food"])) * (D(1) + D("0.25") * (n - 1)) / equiv)
        exp["utilities"] = q2(base * D(str(S["utilities"])))
        exp["transport"] = q2(base * D(str(S["transport"])))
        exp["other"] = q2(base * D(str(S["other"])) * (D(1) - D("0.15") * D(str(round(fd, 6)))))
    hp = ctx.P("P-HEALTH-TRANSITIONS")
    exp["healthcare"] = q2(base * D(str(hp["healthcareShare"].get(st["health"], 0.02))))
    kids_home = [b for b in st["children"] if y - b < 22]
    exp["childCosts"] = q2(base * D(str(S["childShare"])) * len(kids_home))
    exp["education"] = q2(base * D(str(S["childEducationShare"])) * sum(1 for b in kids_home if 6 <= y - b <= 21))
    M = ctx.P("P-MIG-OPPORTUNITY")
    exp["remittancesSent"] = q2(inc["wages"] * D(str(M["remittanceShare"])) * (D(1) + D("0.5") * D(str(round(ctx.trait("familyAttachment"), 6))))) if st["mig"]["abroad"] else ZERO
    a = accs[cur]
    exp["debtInterest"] = q2(a["debt"] * D(str(FN["debtRate"])))
    mrate = D(str(H["mortgageRate"]))
    exp["mortgageInterest"] = q2(a["mortgage"] * mrate)
    exp["migrationCost"] = ZERO
    for pe in st["pending"]:
        if pe["type"] == "migration_cost":
            exp["migrationCost"] += q2(ref_annual * D(pe["years"]))
    # ---------------- gains (all currencies)
    r = ctx.rng(y, "finance:returns")
    shock = st.get("shock") or {}
    ret = D(str(round(FN["investReturn"] + r.gauss(0, FN["investVol"] * ctx.ctl("randomness")) + shock.get("investReturn", 0), 6)))
    for c, ac in accs.items():
        g = gains[c]
        g["investmentReturn"] = q2(ac["investments"] * ret)
        country = next((k for k, v in __import__("app.simulation.inputs", fromlist=["COUNTRY_CURRENCY"]).COUNTRY_CURRENCY.items() if v == c), None)
        ca, cb = (ctx.cpi(country, y - 1), ctx.cpi(country, y)) if country else (None, None)
        app_rate = (cb[0] / ca[0] - 1) if ca and cb else D(str(H["appreciationNoCpi"]))
        g["propertyRevaluation"] = q2(ac["property"] * app_rate)
        g["assetLoss"] = ZERO
        g["businessRevaluation"] = ZERO
    for pe in st["pending"]:
        if pe["type"] == "major_asset_loss":
            for c, ac in accs.items():
                gains[c]["assetLoss"] -= q2((ac["investments"] + ac["property"]) * D(str(O["assetLossShare"])))
        elif pe["type"] == "business_writeoff":
            for c, ac in accs.items():
                gains[c]["businessRevaluation"] -= ac["business"]
        elif pe["type"] == "business_revalue":
            gains[cur]["businessRevaluation"] += q2(a["business"] * (D(pe["multiplier"]) - 1))
    # apply gains to balances
    for c, ac in accs.items():
        g = gains[c]
        ac["investments"] += g["investmentReturn"]
        ac["property"] += g["propertyRevaluation"]
        ac["business"] += g["businessRevaluation"]
        loss = -g["assetLoss"]
        if loss > 0:
            tot = ac["investments"] + ac["property"]
            if tot > 0:
                li = q2(loss * ac["investments"] / tot)
                ac["investments"] -= li
                ac["property"] -= loss - li
        if ac["investments"] < 0:  # negative return beyond holdings cannot happen in reality — floor at zero and book difference
            g["investmentReturn"] -= ac["investments"]
            ac["investments"] = ZERO
        for k, v in other_inc[c].items():
            ac["cash"] += v
    # ---------------- cash flow in residence currency
    total_inc = sum(inc.values(), ZERO)
    total_exp = sum(exp.values(), ZERO)
    a["cash"] += total_inc - total_exp
    notes: list[str] = []
    # pending transfers (purchase, business capital)
    for pe in st["pending"]:
        if pe["type"] == "purchase":
            price, down = q2(D(pe["price"])), q2(D(pe["down"]))
            take = min(down, max(a["cash"], ZERO))
            a["cash"] -= take
            inv_take = min(down - take, a["investments"])
            a["investments"] -= inv_take
            a["property"] += price
            a["mortgage"] += price - take - inv_take
            st["mortgageYearsLeft"] = H["mortgageYears"]
            notes.append(f"Home purchase {cur} {price:.0f}: down payment {take + inv_take:.0f}, mortgage {price - take - inv_take:.0f} (transfer, NW unchanged)")
        elif pe["type"] == "business_capital":
            cap = q2(max(a["cash"], ZERO) * D(pe["share"]))
            a["cash"] -= cap
            a["business"] += cap
            notes.append(f"Business capital {cur} {cap:.0f} moved from cash to business equity (transfer)")
    st["pending"] = []
    # principal repayments
    if a["debt"] > 0 and a["cash"] > 0:
        pay = min(q2(a["debt"] * D(str(FN["debtRepay"]))), a["cash"])
        a["debt"] -= pay
        a["cash"] -= pay
    if a["mortgage"] > 0:
        nleft = max(1, st.get("mortgageYearsLeft") or 1)
        pmt = q2(a["mortgage"] * mrate / (1 - (1 + mrate) ** -nleft)) if mrate > 0 else q2(a["mortgage"] / nleft)
        principal = min(a["mortgage"], max(ZERO, pmt - exp["mortgageInterest"]))
        a["mortgage"] -= principal
        a["cash"] -= principal
        st["mortgageYearsLeft"] = nleft - 1
    # ---------------- shortfall handling
    shortfall_steps = []
    if a["cash"] < 0:
        deficit = -a["cash"]
        cut = min(deficit, q2(exp["other"] * D(str(S["discretionaryCutMax"]))))
        if cut > 0:
            exp["other"] -= cut
            a["cash"] += cut
            total_exp -= cut
            shortfall_steps.append(f"cut discretionary spending by {cut:.0f}")
    if a["cash"] < 0 and a["investments"] > 0:
        sell = min(-a["cash"], a["investments"])
        a["investments"] -= sell
        a["cash"] += sell
        shortfall_steps.append(f"sold investments {sell:.0f}")
    if a["cash"] < 0:
        pr = Prob(FN["familySupport"], "PROVISIONAL_SYSTEM_PRIOR", "family covers part of the shortfall", prior_ids=[ctx.pid("P-FINANCE")])
        pr.add("family attachment", 0.1 * ctx.trait("familyAttachment"))
        if ctx.decide(st, "economics", "family_support", pr, rule="economics.shortfall", what="Receives family support", importance=2):
            sup = q2(-a["cash"] * D("0.5"))
            inc["familySupport"] = sup
            total_inc += sup
            a["cash"] += sup
            shortfall_steps.append(f"family support {sup:.0f}")
    inc.setdefault("familySupport", ZERO)
    if a["cash"] < 0:
        borrow = -a["cash"]
        a["debt"] += borrow
        a["cash"] = ZERO
        shortfall_steps.append(f"borrowed {borrow:.0f}")
    # credit limit: lenders stop once debt passes the distress threshold → remaining needs go unmet (deprivation)
    thr = D(str(FN["distressDebtToIncome"])) / D(str(ctx.ctl("downwardRisk")))
    limit = q2(thr * base * D("1.2"))
    if a["debt"] > limit and shortfall_steps and shortfall_steps[-1].startswith("borrowed"):
        unmet = min(a["debt"] - limit, D(shortfall_steps[-1].split()[-1]))
        a["debt"] -= unmet
        exp["unaffordedConsumption"] = -unmet
        total_exp -= unmet
        shortfall_steps.append(f"credit exhausted: {unmet:.0f} of needs went unmet (deprivation)")
        if not st["flags"].get("deprivation"):
            st["flags"]["deprivation"] = True
            ctx.record(st, "economics", "deprivation", f"Credit exhausted (limit {limit:.0f}); {cur} {unmet:.0f} of household needs could not be paid.",
                       rule="economics.credit_limit", importance=3, prior_ids=[ctx.pid("P-FINANCE")])
    elif st["flags"].get("deprivation") and not shortfall_steps:
        st["flags"]["deprivation"] = False
    # savings allocation
    buffer = q2(total_exp * D("0.5"))
    if a["cash"] > buffer and a["debt"] == 0:
        share = D(str(round(min(0.9, max(0.0, FN["investShare"] + 0.15 * ctx.trait("riskTolerance"))), 6)))
        mv = q2((a["cash"] - buffer) * share)
        a["cash"] -= mv
        a["investments"] += mv
    # distress
    debt_ratio = (a["debt"] / base) if base > 0 else D(0)
    if debt_ratio > thr:
        st["distressYears"] = st.get("distressYears", 0) + 1
        if not st["flags"].get("distress"):
            ctx.record(st, "economics", "financial_distress", f"Debt {a['debt']:.0f} exceeds {thr:.1f}× household resources ({base:.0f}) — financial distress "
                       f"(threshold from prior P-FINANCE ÷ downward-risk control).", rule="economics.distress", importance=3, prior_ids=[ctx.pid("P-FINANCE")],
                       cls="DETERMINISTIC")
        st["flags"]["distress"] = True
        if st["distressYears"] >= 3 and a["property"] > 0:
            sale = a["property"]
            a["cash"] += sale
            a["property"] = ZERO
            repay = min(a["mortgage"], a["cash"])
            a["mortgage"] -= repay
            a["cash"] -= repay
            repay2 = min(a["debt"], a["cash"])
            a["debt"] -= repay2
            a["cash"] -= repay2
            st["housing"] = "rent"
            ctx.record(st, "housing", "forced_sale", f"Property sold ({cur} {sale:.0f}) after {st['distressYears']} years of financial distress; mortgage and debt repaid.",
                       rule="economics.forced_sale", importance=3)
    else:
        if st["flags"].get("distress") and debt_ratio < thr / 2:
            ctx.record(st, "economics", "distress_resolved", "Debt back below half the distress threshold.", rule="economics.distress", importance=2)
            st["flags"]["distress"] = False
            st["distressYears"] = 0
    if a["mortgage"] <= 0 and st["housing"] == "mortgaged":
        st["housing"] = "owned"
    # ---------------- reconciliation
    closing = {c: nw(ac) for c, ac in accs.items()}
    recon = {}
    for c in accs:
        i = total_inc if c == cur else sum(other_inc[c].values(), ZERO)
        e = total_exp if c == cur else ZERO
        g = sum(gains[c].values(), ZERO)
        expected = opening.get(c, ZERO) + i - e + g + tr.get(c, ZERO)
        recon[c] = {"opening": str(q2(opening.get(c, ZERO))), "income": str(q2(i)), "expenses": str(q2(e)), "gains": str(q2(g)),
                    "transfers": str(q2(tr.get(c, ZERO))), "closing": str(q2(closing[c])), "difference": str(q2(closing[c] - expected))}
    _store(st, accs)
    L = st["life"]
    L["earnings"][cur] = str(q2(D(L["earnings"].get(cur, "0")) + inc["wages"]))
    L["spending"][cur] = str(q2(D(L["spending"].get(cur, "0")) + total_exp))
    if inc["wages"] > D(L["peakIncome"].get(cur, "0")):
        L["peakIncome"][cur] = str(inc["wages"])
    for c, v in closing.items():
        if v > D(L["peakNetWorth"].get(c, "-1e30")):
            L["peakNetWorth"][c] = str(q2(v))
    emp = st["emp"]["state"]
    if emp in ("employee", "self_employed", "business_owner"):
        L["yearsEmployed"] += 1
    elif emp == "unemployed" and st["emp"].get("firstJobYear") is not None:
        L["yearsUnemployed"] += 1
    elif emp == "retired":
        L["yearsRetired"] += 1
    return {"currency": cur, "income": {k: str(v) for k, v in inc.items()}, "expenses": {k: str(v) for k, v in exp.items()},
            "gains": {c: {k: str(v) for k, v in g.items()} for c, g in gains.items()}, "totalIncome": str(q2(total_inc)), "totalExpenses": str(q2(total_exp)),
            "netIncome": str(q2(total_inc - total_exp)), "balances": st["acc"], "netWorth": {c: str(q2(v)) for c, v in closing.items()},
            "reconciliation": recon, "shortfall": shortfall_steps, "notes": notes, "householdSize": n, "subsistenceFloor": str(floor),
            "wageProvenance": None if ref is None else {"class": ref["class"], "anchorId": ref["anchorId"], "anchorYear": ref["anchorYear"], "method": ref["method"],
                                                        "priorIds": ref["priorIds"], "evidenceIds": ref["evidenceIds"], "assumptionIds": ref["assumptionIds"],
                                                        "grossOrNet": ref["grossOrNet"], "value": "SIMULATED"},
            "priorIds": sorted(prior_used), "assumptionIds": sorted(asm_used), "valueStatus": "SIMULATED"}
