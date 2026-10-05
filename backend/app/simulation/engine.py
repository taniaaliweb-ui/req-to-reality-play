"""Year-by-year life engine. simulate(payload, seed) is a pure function of the frozen input:
same payload + seed + overrides + engine version → identical life."""
from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal

from app.simulation import ENGINE_VERSION
from app.simulation.context import Ctx, D
from app.simulation.economics import step as econ_step
from app.simulation.inputs import COUNTRY_CURRENCY
from app.simulation.rules import career, education, fertility, health, housing, migration, mortality, outliers, relationships, retirement


def init_state(ctx: Ctx) -> dict:
    ch = ctx.ch
    c = ch["country"]
    cur = COUNTRY_CURRENCY.get(c, c)
    return {"year": ch["birthYear"], "age": 0, "alive": True, "country": c, "city": ch.get("region") or "", "currency": cur,
            "edu": {"state": "not_started", "level": "none", "yearsInLevel": 0},
            "emp": {"state": "child", "occupation": None, "seniority": 0, "experience": 0, "wageFactor": 1.0, "firstJobYear": None, "unemployedYears": 0, "business": None},
            "rel": {"state": "not_present", "partner": None}, "children": [], "housing": "family_home", "health": "good",
            "mig": {"origin": c, "abroad": False, "count": 0, "failed": 0, "returned": False, "history": []},
            "ret": {"state": "working", "age": None, "pension": "0"},
            "acc": {cur: {"cash": "0.00", "investments": "0.00", "property": "0.00", "business": "0.00", "debt": "0.00", "mortgage": "0.00"}},
            "mortgageYearsLeft": 0, "distressYears": 0, "pending": [], "transfers": [], "flags": {},
            "life": {"earnings": {}, "spending": {}, "peakIncome": {}, "peakNetWorth": {}, "yearsEmployed": 0, "yearsUnemployed": 0, "yearsRetired": 0,
                     "businessAttempts": 0, "businessSuccess": 0, "homeOwned": False, "outliers": [], "countries": [c], "retirementAge": None}}


def _shocks(ctx: Ctx, st: dict) -> None:
    eff = ctx.P("P-SHOCK-EFFECTS")
    out = {"eventIds": []}
    y = st["year"]
    for e in ctx.ev["events"]:
        if e["verification"] != "verified":
            continue
        y0 = int(str(e.get("start") or "0")[:4] or 0)
        y1 = int(str(e.get("end") or e.get("start") or "0")[:4] or y0)
        geo = set(e.get("geography") or [])
        if not (y0 <= y <= y1) or not (st["country"] in geo or "WORLD" in geo or ("GCC" in geo and st["country"] in {"ARE", "SAU", "QAT", "KWT", "OMN", "BHR"})):
            continue
        fx = eff.get(e["category"]) or {}
        if not fx:
            continue
        out["eventIds"].append(e["id"])
        for k, v in fx.items():
            out[k] = (out.get(k, 1.0) * v) if k in ("jobLoss", "migration") else out.get(k, 0.0) + v
        if e["id"] not in st["flags"].setdefault("shocksNoted", []):
            st["flags"]["shocksNoted"].append(e["id"])
            ctx.record(st, "historical", "historical_shock", f"Verified historical event '{e['name']}' active: effects {fx} (prior P-SHOCK-EFFECTS).",
                       rule="historical.shock", importance=2, evidence_ids=[e["id"]], prior_ids=[ctx.pid("P-SHOCK-EFFECTS")])
    st["shock"] = out if out["eventIds"] else {}


def _public_state(st: dict) -> dict:
    return {k: v for k, v in st.items() if k not in ("pending", "transfers")}


def simulate(payload: dict, seed: int, overrides: list[dict] | None = None, start_state: dict | None = None, max_years: int = 130) -> dict:
    ctx = Ctx(payload, seed, overrides)
    if start_state is None:
        st = init_state(ctx)
        ctx.record(st, "life", "birth", f"Born {st['year']} in {ctx.ch.get('region') or ''}, {ctx.ch.get('countryName') or st['country']} (Character DNA).",
                   rule="life.birth", importance=3)
    else:
        st = copy.deepcopy(start_state)
        st["year"] += 1
        st["age"] += 1
        st.setdefault("pending", [])
        st.setdefault("transfers", [])
    states = []
    for _ in range(max_years):
        _shocks(ctx, st)
        health.step(ctx, st)
        education.step(ctx, st)
        career.step(ctx, st)
        relationships.step(ctx, st)
        fertility.step(ctx, st)
        migration.step(ctx, st)
        housing.step(ctx, st)
        retirement.step(ctx, st)
        outliers.step(ctx, st)
        econ = econ_step(ctx, st)
        died = mortality.step(ctx, st)
        if died:
            st["alive"] = False
            prev_emp = st["emp"]["state"]
            st["emp"]["state"] = "deceased"
            if st["rel"]["state"] in ("married", "partnered") and (st["rel"].get("partner") or {}).get("alive"):
                st["rel"]["state"] = "deceased (partner survives)"
            ctx.record(st, "life", "estate", f"Death closes employment ({prev_emp}), income and household role. Final estate (net worth by currency): "
                       + ", ".join(f"{c} {v}" for c, v in econ["netWorth"].items()), rule="life.estate", importance=2)
        states.append({"year": st["year"], "age": st["age"], "country": st["country"], "employment": st["emp"]["state"], "currency": st["currency"],
                       "income": econ["income"]["wages"], "netWorth": econ["netWorth"].get(st["currency"], "0"), "economics": econ, "state": _public_state(copy.deepcopy(st))})
        if died:
            break
        st["year"] += 1
        st["age"] += 1
    events = ctx.events
    for i, e in enumerate(events):
        e["seq"] = i
    return {"states": states, "events": events, "outcome": outcome(payload, states, events), "engineVersion": ENGINE_VERSION, "seed": seed}


def outcome(payload: dict, states: list[dict], events: list[dict]) -> dict:
    last = states[-1]
    L = last["state"]["life"]
    occ = lambda t: any(e["eventType"] == t and e["occurred"] for e in events)  # noqa: E731
    final_cur = last["currency"]
    nw_death = last["economics"]["netWorth"]
    first30 = next((s for s in states if s["age"] == 30), None)
    pos = None
    if first30 and last["age"] >= 45:
        ref = D(first30["economics"]["subsistenceFloor"] or "1") or D(1)
        a = D(first30["netWorth"]) / ref
        b = D(nw_death.get(final_cur, "0")) / (D(last["economics"]["subsistenceFloor"] or "1") or D(1))
        pos = "improved" if b - a > 2 else "declined" if a - b > 2 else "stable"
    return {"deathYear": last["year"] if not last["state"]["alive"] else None, "deathAge": last["age"] if not last["state"]["alive"] else None,
            "lifetimeEarnings": L["earnings"], "lifetimeSpending": L["spending"], "peakIncome": L["peakIncome"], "peakNetWorth": L["peakNetWorth"],
            "netWorthAtDeath": nw_death, "finalCurrency": final_cur, "yearsEmployed": L["yearsEmployed"], "yearsUnemployed": L["yearsUnemployed"],
            "yearsRetired": L["yearsRetired"], "retirementAge": L.get("retirementAge"), "children": len(last["state"]["children"]),
            "migrated": occ("migration"), "homeOwner": L["homeOwned"], "businessAttempt": L["businessAttempts"] > 0, "businessSuccess": L["businessSuccess"] > 0,
            "married": occ("marriage"), "divorced": occ("divorce"), "outliers": L["outliers"], "countries": L["countries"],
            "education": last["state"]["edu"]["level"], "economicPosition": pos,
            "economicPositionDefinition": "Net worth in units of the household subsistence floor at age 30 vs at death; ±2 units = improved/declined.",
            "label": "SIMULATED"}


def fingerprint(result: dict) -> str:
    """Hash of everything that defines the life (used for reproducibility proofs)."""
    core = {"events": [{k: e[k] for k in ("year", "age", "domain", "eventType", "probability", "randomDraw", "outcome")} for e in result["events"]],
            "states": [{k: s[k] for k in ("year", "age", "country", "employment", "income", "netWorth")} for s in result["states"]]}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def resume_state(states: list[dict], year: int) -> dict | None:
    """Full engine state at the END of year-1 (branch point is `year`)."""
    prev = next((s for s in states if s["year"] == year - 1), None)
    if prev is None:
        return None
    st = copy.deepcopy(prev["state"])
    st["pending"], st["transfers"] = [], []
    return st


_ = Decimal  # re-export guard
