"""Simulation audit + quality report (no fake 'accuracy score')."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from app.simulation.inputs import COUNTRY_CURRENCY


def audit_run(payload: dict, states: list[dict], events: list[dict]) -> list[dict]:
    out: list[dict] = []

    def add(rule, sev, msg, year=None):
        if len([x for x in out if x["ruleId"] == rule]) < 20:
            out.append({"ruleId": rule, "severity": sev, "message": msg, "year": year})

    b = payload["character"]["birthYear"]
    asm_ids = {a["id"] for a in payload["assumptions"]}
    death = next((e for e in events if e["eventType"] == "death" and e["occurred"]), None)
    prev_year = b
    for e in events:
        p = e.get("probability")
        if p is not None and not (0 <= p <= 1):
            add("probability-range", "error", f"Probability {p} outside [0,1] for {e['eventType']}", e["year"])
        if e["probabilityClass"] not in ("DETERMINISTIC",) and p is not None and not e.get("probabilitySourceIds"):
            add("unsupported-probability", "error", f"{e['eventType']} ({e['year']}) has a probability without any evidence, assumption or prior source", e["year"])
        if not e.get("probabilityClass"):
            add("missing-provenance", "error", f"{e['eventType']} has no probability class", e["year"])
        for a in e.get("assumptionIds") or []:
            if a not in asm_ids:
                add("untraceable-assumption", "error", f"{e['eventType']} cites assumption {a} that is not in the frozen input", e["year"])
        if e["year"] < prev_year:
            add("chronology", "error", f"Event {e['eventType']} in {e['year']} recorded after {prev_year}", e["year"])
        prev_year = max(prev_year, e["year"])
        if e["age"] != e["year"] - b:
            add("age-mismatch", "error", f"{e['eventType']}: age {e['age']} ≠ {e['year']} − {b}", e["year"])
        if death and e["seq"] > death["seq"] and e["eventType"] not in ("estate",):
            add("event-after-death", "error", f"{e['eventType']} occurs after death", e["year"])
        if e["eventType"] == "first_job" and e["age"] < 12:
            add("impossible-age", "error", f"First job at age {e['age']}", e["year"])
        if e["eventType"] == "marriage" and e["occurred"] and e["age"] < 16:
            add("impossible-age", "error", f"Marriage at age {e['age']}", e["year"])
    broad_seen: set = set()
    for s in states:
        st, econ = s["state"], s["economics"]
        if s["age"] != s["year"] - b:
            add("age-mismatch", "error", f"State {s['year']} age {s['age']}", s["year"])
        for c, r in econ["reconciliation"].items():
            if Decimal(r["difference"]) != 0:
                add("financial-mismatch", "error", f"{s['year']} {c}: closing net worth differs from opening + flows by {r['difference']}", s["year"])
        if COUNTRY_CURRENCY.get(s["country"], s["currency"]) != s["currency"]:
            add("currency-mismatch", "error", f"{s['year']}: residence {s['country']} but ledger currency {s['currency']}", s["year"])
        wp = econ.get("wageProvenance")
        if wp and wp.get("grossOrNet") == "NET" and Decimal(econ["expenses"].get("tax", "0")) > 0:
            add("gross-net-confusion", "error", f"{s['year']}: tax applied to a NET wage anchor", s["year"])
        if wp and wp.get("grossOrNet") == "UNKNOWN" and s["age"] % 10 == 0:
            add("gross-net-unknown", "warning", f"{s['year']}: wage anchor gross/net unknown — tax prior applied to a value of unknown basis", s["year"])
        if st["emp"].get("occupation") == "professional" and st["edu"]["level"] not in ("tertiary",) and st["edu"]["state"] == "completed":
            add("occupation-inconsistency", "warning", f"{s['year']}: professional occupation without tertiary education", s["year"])
        ml = st.get("mortality") or {}
        if ml and not ml.get("ageSpecificAvailable") and ml.get("country") not in broad_seen:
            broad_seen.add(ml.get("country"))
            add("mortality-broad-fallback", "warning", f"{s['year']}: no age-specific life table in the snapshot for {ml.get('country')} — broad measure "
                f"({ml.get('sourceIndicator')}, {ml.get('formulaId')}) used. Sync UN WPP life tables and re-snapshot.", s["year"])
        if ml and ml.get("annualProbability") is None:
            add("mortality-lineage", "error", f"{s['year']}: mortality hazard has no annual probability lineage", s["year"])
        for step in (wp or {}).get("chain") or []:
            if step["step"] == "final" and step.get("classification") != "SIMULATED":
                add("wage-marked-evidence", "error", f"{s['year']}: final wage not labelled SIMULATED", s["year"])
        if econ.get("valueStatus") != "SIMULATED":
            add("simulation-marked-fact", "error", f"{s['year']}: economic values not labelled SIMULATED", s["year"])
    kids = [e for e in events if e["eventType"] == "child_born" and e["occurred"]]
    for k in kids:
        if payload["character"]["sex"] == "FEMALE" and not (12 <= k["age"] <= 55):
            add("impossible-age", "error", f"Child born at mother age {k['age']}", k["year"])
    death_year = death["year"] if death else None
    for lk in payload["locks"]:
        if not lk.get("kind"):
            continue
        if death_year is not None and lk["year"] > death_year:
            add("locked-event-conflict", "error", f"Locked event '{lk['title']}' ({lk['year']}) is after simulated death ({death_year})", lk["year"])
            continue
        if not any(e["outcome"] == "FORCED" and lk["id"] in (e.get("factIds") or []) for e in events) and lk["kind"] not in ("first_job",):
            add("locked-event-conflict", "warning", f"Locked event '{lk['title']}' ({lk['year']}) was not applied (state made it inapplicable)", lk["year"])
    for a in payload["evidence"]["wageAnchors"]:
        if a.get("class") == "EMPIRICAL" and not a.get("evidenceIds") and not a.get("factIds"):
            add("prototype-as-verified", "warning", f"Wage anchor {a['id']} is labelled empirical but has no linked observation", None)
    return out


def quality_report(payload: dict, states: list[dict], events: list[dict], audit: list[dict]) -> dict:
    cls = Counter(e["probabilityClass"] for e in events if e["probability"] is not None or e["outcome"] in ("FORCED", "SCENARIO_OVERRIDE"))
    stoch = [e for e in events if e["probability"] is not None]
    traced = [e for e in stoch if e.get("probabilitySourceIds") and e.get("randomDraw") is not None]
    prior_use = Counter(p for e in events for p in e.get("priorIds") or [])
    for s in states:
        for p in s["economics"].get("priorIds") or []:
            prior_use[p] += 1
    asm_use = Counter(a for e in events for a in e.get("assumptionIds") or [])
    for s in states:
        for a in s["economics"].get("assumptionIds") or []:
            asm_use[a] += 1
    wage_cls = Counter((s["economics"].get("wageProvenance") or {}).get("class") for s in states if s["economics"].get("wageProvenance"))
    recon = [r for s in states for r in s["economics"]["reconciliation"].values()]
    bad = [r for r in recon if Decimal(r["difference"]) != 0]
    rv = payload.get("review") or {}
    unverified = [e["id"] for e in payload["evidence"]["events"] if e["verification"] != "verified"]
    return {
        "evidenceCoverage": [{"dimension": d["label"], "evidence": d["evidenceStatus"], "simulation": d["simulationStatus"]} for d in rv.get("dimensions", [])],
        "assumptionDependency": {"assumptionsUsed": dict(asm_use), "eventsAssumptionBased": cls.get("ASSUMPTION_BASED", 0)},
        "provisionalPriorDependency": {"eventsPriorBased": cls.get("PROVISIONAL_SYSTEM_PRIOR", 0), "priorsUsed": dict(prior_use.most_common()),
                                       "wageYearsByClass": dict(wage_cls)},
        "economicConsistency": {"ledgerLines": len(recon), "reconciled": len(recon) - len(bad), "mismatches": len(bad)},
        "chronology": {"errors": sum(1 for a in audit if a["ruleId"] in ("chronology", "age-mismatch", "event-after-death"))},
        "probabilityProvenance": {"stochasticEvents": len(stoch), "fullyTraced": len(traced), "byClass": dict(cls)},
        "missingEvidence": {"dimensions": [d["label"] for d in rv.get("dimensions", []) if d["evidenceStatus"] == "MISSING"],
                            "unverifiedHistoricalEventsExcluded": unverified},
        "auditWarnings": {"errors": sum(1 for a in audit if a["severity"] == "error"), "warnings": sum(1 for a in audit if a["severity"] == "warning")},
        "note": "No single accuracy score is computed: the life is SIMULATED under the listed evidence, assumptions and provisional priors.",
    }
