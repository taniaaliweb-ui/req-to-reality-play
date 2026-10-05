"""Housing tenure: family_home → rent | shared → owned/mortgaged (purchase needs a down payment).
Costs come from housing assumptions (amount or share) when present, else prior P-HOUSING shares — never labelled verified."""
from __future__ import annotations

from app.simulation.context import D
from app.simulation.probability import Prob
from app.simulation.rules.career import liquid


def step(ctx, st) -> None:
    H = ctx.P("P-HOUSING")
    emp, y = st["emp"], st["year"]
    working = emp["state"] in ("employee", "self_employed", "business_owner")
    if st["housing"] == "family_home" and working and st["age"] >= 18:
        pr = Prob(H["leaveHome"], "PROVISIONAL_SYSTEM_PRIOR", "annual move out of the family home", prior_ids=[ctx.pid("P-HOUSING")])
        if st["rel"]["state"] == "married":
            pr.add("married", 0.3, "state")
        if ctx.decide(st, "housing", "move_out", pr, rule="housing.leave_home", what="Moves out to rented housing", importance=2,
                      before={"housing": "family_home"}, after={"housing": "rent"}):
            st["housing"] = "rent"
        return
    if st["housing"] in ("rent", "shared", "employer_housing", "family_home") and working and 25 <= st["age"] <= 65:
        inc = D(st.get("lastHouseholdIncome") or "0")
        if inc <= 0:
            return
        price = inc * D(str(H["priceToIncome"]))
        down = price * D(str(H["downPayment"]))
        if liquid(st, st["currency"]) < down:
            return
        pr = Prob(H["purchase"], "PROVISIONAL_SYSTEM_PRIOR", "annual home purchase when a down payment is affordable", prior_ids=[ctx.pid("P-HOUSING")])
        pr.add("financial discipline", 0.03 * ctx.trait("financialDiscipline"))
        if ctx.decide(st, "housing", "purchase", pr, rule="housing.purchase", what=f"Buys a home (price {H['priceToIncome']}× household income, prior)",
                      importance=3, record_no=st["age"] % 5 == 0, before={"housing": st["housing"]}, after={"housing": "mortgaged"}):
            st["pending"].append({"type": "purchase", "price": str(price), "down": str(down)})
            st["housing"] = "mortgaged"
            st["life"]["homeOwned"] = True
