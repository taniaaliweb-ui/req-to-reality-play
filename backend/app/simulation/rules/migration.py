"""Migration: opportunity → consideration → success | failure; return migration; second migration.
Destinations come only from evidenced migration paths in the snapshot or locked timeline events — national
migration figures are context, not individual probabilities. Money already held stays in its currency unless a
period-average FX observation for both currencies exists in the snapshot (then it is converted, DERIVED)."""
from __future__ import annotations

from decimal import Decimal

from app.simulation.context import D, q2
from app.simulation.inputs import COUNTRY_CURRENCY
from app.simulation.probability import Prob


def _move(ctx, st, dest: str, city: str, why_event: dict | None):
    old_c, old_cur = st["country"], st["currency"]
    new_cur = COUNTRY_CURRENCY.get(dest, dest)
    st["country"], st["city"], st["currency"] = dest, city, new_cur
    st["acc"].setdefault(new_cur, {"cash": "0", "investments": "0", "property": "0", "business": "0", "debt": "0", "mortgage": "0"})
    fo, fd = ctx.fx(old_c, st["year"]), ctx.fx(dest, st["year"])
    note = ""
    if fo and fd and old_cur != new_cur:
        cash = D(st["acc"][old_cur]["cash"])
        if cash > 0:
            conv = q2(cash / fo[0] * fd[0])
            st["acc"][old_cur]["cash"] = "0.00"
            st["acc"][new_cur]["cash"] = str(q2(D(st["acc"][new_cur]["cash"]) + conv))
            st["transfers"].append({"currency": old_cur, "amount": str(-q2(cash))})
            st["transfers"].append({"currency": new_cur, "amount": str(conv)})
            note = f" Cash {old_cur} {cash:.0f} converted to {new_cur} {conv:.0f} at World Bank period-average rates ({fo[1]}, {fd[1]}) [DERIVED]."
    elif old_cur != new_cur:
        note = f" No FX evidence pair for {st['year']}: balances stay in {old_cur} (no conversion invented)."
    M = ctx.P("P-MIG-OPPORTUNITY")
    if dest != st["mig"]["origin"]:
        r = ctx.rng(st["year"], "migration:housing").random()
        st["housing"] = "employer_housing" if r < M["employerHousing"] else "shared" if st["rel"]["state"] not in ("married",) else "rent"
        note += f" Housing on arrival: {st['housing']} (prior P-MIG-OPPORTUNITY employerHousing {M['employerHousing']})."
    else:
        st["housing"] = "family_home" if st["housing"] in ("employer_housing", "shared") else st["housing"]
    st["mig"]["abroad"] = dest != st["mig"]["origin"]
    st["mig"]["history"].append({"year": st["year"], "from": old_c, "to": dest})
    if dest not in st["life"]["countries"]:
        st["life"]["countries"].append(dest)
    if why_event is not None:
        why_event["explanation"] += note
        why_event["stateAfter"] = {"country": dest, "currency": new_cur}


def step(ctx, st) -> None:
    y, a, mig = st["year"], st["age"], st["mig"]
    lk = ctx.lock("migration", y)
    if lk and lk.get("country") and lk["country"] != st["country"]:
        e = ctx.forced(st, "migration", "migration" if lk["country"] != mig["origin"] else "return_migration",
                       f"Move to {lk['location']} fixed by locked timeline event '{lk['title']}'.", rule="migration.locked", lock_id=lk["id"],
                       before={"country": st["country"]})
        mig["count"] += 1
        _move(ctx, st, lk["country"], lk.get("city") or "", e)
        return
    if any(l["kind"] == "migration" for l in ctx.locks):
        return  # locked migration history defines the moves; no extra simulated migrations
    M = ctx.P("P-MIG-OPPORTUNITY")
    if st["emp"]["state"] == "retired" or not (M["minAge"] <= a <= M["maxAge"]):
        return
    shock = st.get("shock") or {}
    if mig["abroad"]:
        pr = Prob(M["returnAnnual"], "PROVISIONAL_SYSTEM_PRIOR", "annual return migration", prior_ids=[ctx.pid("P-MIG-OPPORTUNITY")])
        ctx.tadd(pr, "returnMigration")
        if st["emp"]["state"] == "unemployed":
            ctx.smod(pr, "unemployed abroad", "returnUnemployedAbroadAdd", "add")
        if ctx.decide(st, "migration", "return_migration", pr, rule="migration.return", what=f"Returns to {mig['origin']}", importance=3,
                      before={"country": st["country"]}):
            _move(ctx, st, mig["origin"], ctx.ch.get("region") or "", ctx.events[-1])
            mig["returned"] = True
        return
    if mig["count"] >= ctx.sm("maxMigrations"):
        return
    paths = [p for p in ctx.ev["migrationPaths"] if p["origin"] == st["country"] and p["yearStart"] - ctx.window("migrationPathYears") <= y <= p["yearEnd"] + ctx.window("migrationPathYears")]
    if not paths:
        return
    if ctx.override("no_migration"):
        if not st["flags"].get("noMigrationNoted"):
            st["flags"]["noMigrationNoted"] = True
            ctx.forced(st, "migration", "no_migration", "SCENARIO OVERRIDE: does not migrate", rule="migration.override", override=True)
        return
    p = paths[0]
    pr = Prob(M["withPath"], "PROVISIONAL_SYSTEM_PRIOR", f"annual migration opportunity on evidenced path {p['origin']}→{p['destination']}",
              prior_ids=[ctx.pid("P-MIG-OPPORTUNITY")], evidence_ids=[p["id"]])
    ctx.tadd(pr, "migration")
    if st["emp"]["state"] == "unemployed":
        ctx.smod(pr, "unemployed", "migrateUnemployedAdd", "add")
    o_ref, d_ref = ctx.any_ref_wage(st["country"], y), ctx.any_ref_wage(p["destination"], y)
    fo, fd = ctx.fx(st["country"], y), ctx.fx(p["destination"], y)
    if o_ref and d_ref and fo and fd:
        ratio = (d_ref["annual"] / fd[0]) / (o_ref["annual"] / fo[0])
        if ratio > Decimal(str(ctx.sm("wageOpportunityMinRatio"))):
            pr.add(f"wage opportunity (destination/origin reference wage in USD ≈ {ratio:.1f}×)", min(ctx.sm("wageOpportunityCap"), ctx.sm("wageOpportunityPerRatio") * float(ratio)), "evidence")
            pr.prior_ids.append(ctx.pid("P-STATE-MODIFIERS"))
            pr.evidence_ids += [fo[1], fd[1]] + d_ref["evidenceIds"]
    if shock.get("migration"):
        pr.mult("verified historical shock", shock["migration"], "evidence")
    if not ctx.decide(st, "migration", "migration_opportunity", pr, rule="migration.opportunity", what=f"Pursues migration to {p['destination']}",
                      importance=3, record_no=True, before={"country": st["country"]}):
        return
    fp = Prob(M["failure"], "PROVISIONAL_SYSTEM_PRIOR", "migration attempt fails (visa/job falls through)", prior_ids=[ctx.pid("P-MIG-OPPORTUNITY")]).mult("adversity control", ctx.ctl("adversity"))
    if ctx.decide(st, "migration", "failed_migration", fp, rule="migration.failure", what="Migration attempt fails", importance=3):
        mig["failed"] += 1
        st["pending"].append({"type": "migration_cost", "years": str(ctx.sm("migrationFailureCostYears"))})
        return
    mig["count"] += 1
    e = ctx.record(st, "migration", "migration", f"Migrates to {p['destination']} (successful attempt after opportunity draw).", rule="migration.success",
                   importance=3, before={"country": st["country"]}, prior_ids=[ctx.pid("P-MIG-OPPORTUNITY")], evidence_ids=[p["id"]], cls="PROVISIONAL_SYSTEM_PRIOR")
    e["outcome"] = "OCCURRED"
    _move(ctx, st, p["destination"], "", e)
