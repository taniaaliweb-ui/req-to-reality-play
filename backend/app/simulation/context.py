"""Simulation context: frozen input access, evidence lookups, config/trait modifiers and event recording.

CONFIGURATION CONTROLS (0–100, default 50 → neutral). Documented mathematical effects:
  realism            trait influence scale s = 1.5 − realism/100 (high realism damps trait modifiers toward base rates)
  randomness         wage-position sd × (0.5 + r); investment-return volatility × (0.5 + r)
  adversity          × (0.5 + a) on negative life events (health onset, separation, migration failure, negative outliers)
  upwardMobility     × (0.5 + u) on promotion, business success, positive outliers
  downwardRisk       × (0.5 + d) on job loss, business failure; financial-distress debt threshold ÷ (0.5 + d)
  careerVolatility   × (0.5 + c) on job change, job loss, business start
  relationshipVolatility × (0.5 + v) on new partnership and separation
  healthIntensity    × (0.5 + h) on health-condition onset
  outlierIntensity   × (0.25 + 1.5·o) on rare outcomes
TRAIT MODIFIERS (t = trait/100; centred c = 2t − 1 ∈ [−1, 1], scaled by realism s) are additive probability
points; see TRAIT_EFFECTS. Traits are modifiers, never guarantees.
"""
from __future__ import annotations

import math
from decimal import Decimal

from app.simulation.probability import Prob, trace_text, weakest
from app.simulation.random import stream

TRAIT_EFFECTS = [
    ("aptitude", "school enrollment / progression", "+0.08·c"), ("aptitude", "university entry", "+0.15·c"), ("aptitude", "promotion", "+0.03·c"),
    ("ambition", "promotion", "+0.04·c"), ("ambition", "university entry", "+0.06·c"), ("ambition", "business start", "+0.008·c"),
    ("discipline", "school dropout", "−0.02·c"), ("discipline", "job loss", "−0.012·c"),
    ("riskTolerance", "business start", "+0.012·c"), ("riskTolerance", "investment share", "+0.15·c (allocation, not a probability)"),
    ("socialSkills", "new partnership", "+0.04·c"), ("socialSkills", "re-employment", "+0.08·c"),
    ("financialDiscipline", "home purchase", "+0.03·c"), ("financialDiscipline", "discretionary spending", "−15%·c of the 'other' share"),
    ("resilience", "re-employment", "+0.06·c"), ("resilience", "health recovery", "+0.1·c"),
    ("familyAttachment", "migration", "−0.015·c"), ("familyAttachment", "return migration", "+0.03·c"), ("familyAttachment", "remittance share", "×(1+0.5·c)"),
    ("migrationWillingness", "migration", "+0.025·c"),
]
NEGATIVE = "adversity"
TRAIT_KEYS = {"socialAbility": "socialSkills"}


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def q2(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"))


class Ctx:
    def __init__(self, payload: dict, seed: int, overrides: list[dict] | None = None):
        self.p = payload
        self.seed = seed
        self.overrides = overrides or []
        self.cfg = payload["config"]
        self.ch = payload["character"]
        self.ev = payload["evidence"]
        self.priors = payload["priors"]
        self.events: list[dict] = []
        self.locks = payload["locks"]
        self.assumptions = payload["assumptions"]

    # ----------------------------------------------------------------- registry / config / traits
    def _prior(self, key: str) -> dict:
        if key in self.priors:
            return self.priors[key]
        # frozen input created before this registry entry existed → code default (identical to the former inline value)
        from app.simulation.priors import defaults
        return defaults()[key]

    def P(self, key: str) -> dict:
        return self._prior(key)["parameter"]

    def pid(self, key: str) -> str:
        return self._prior(key)["id"]

    def prior_enabled(self, key: str) -> bool:
        return key in self.priors and self.priors[key]["enabled"]

    def ctl(self, name: str) -> float:
        C = self.P("P-CONTROL-SCALING")
        v = self.cfg.get(name, 50) / 100  # rule:R-SLIDER-NEUTRAL
        return C["outlierBase"] + C["outlierSlope"] * v if name == "outlierIntensity" else C["neutralOffset"] + v

    def trait(self, name: str) -> float:
        tr = self.ch.get("traits") or {}
        t = tr.get(name, tr.get(next((k for k, v in TRAIT_KEYS.items() if v == name), name), 50))  # rule:R-SLIDER-NEUTRAL
        return (2 * (float(t) / 100) - 1) * (self.P("P-CONTROL-SCALING")["realismBase"] - self.cfg.get("realism", 50) / 100)  # rule:R-TRAIT-CENTRE

    # ----------------------------------------------------------------- registry shortcuts (every value is a versioned prior)
    def age_bound(self, name: str):
        return self.P("P-AGE-BOUNDS")[name]

    def window(self, name: str):
        return self.P("P-EVIDENCE-WINDOWS")[name]

    def sm(self, name: str):
        return self.P("P-STATE-MODIFIERS")[name]

    def er(self, name: str):
        return self.P("P-ECON-RULES")[name]

    def tval(self, effect: str, trait: str) -> float:
        return self.P("P-TRAIT-EFFECTS")[effect][trait] * self.trait(trait)

    def tadd(self, pr: Prob, effect: str) -> Prob:
        for t, coef in self.P("P-TRAIT-EFFECTS")[effect].items():
            pr.add(f"{t} (trait effect {effect})", coef * self.trait(t), "trait")
        pid = self.pid("P-TRAIT-EFFECTS")
        if pid not in pr.prior_ids:
            pr.prior_ids.append(pid)
        return pr

    def smod(self, pr: Prob, label: str, name: str, kind: str = "mult") -> Prob:
        v = self.sm(name)
        (pr.mult if kind == "mult" else pr.add)(label, v, "state")
        pid = self.pid("P-STATE-MODIFIERS")
        if pid not in pr.prior_ids:
            pr.prior_ids.append(pid)
        return pr

    def rng(self, year: int, domain: str):
        return stream(self.seed, year, domain)

    def override(self, kind: str, year: int | None = None) -> dict | None:
        for o in self.overrides:
            if o["type"] == kind and (year is None or o.get("year") in (None, year) or (o.get("fromYear") is not None and year >= o["fromYear"])):
                return o
        return None

    def lock(self, kind: str, year: int) -> dict | None:
        return next((l for l in self.locks if l["kind"] == kind and l["year"] == year), None)

    def last_lock_year(self) -> int | None:
        ys = [l["year"] for l in self.locks if l["kind"] != "death"]
        return max(ys) if ys else None

    # ----------------------------------------------------------------- evidence lookups (frozen snapshot only)
    def series(self, metric: str, country: str, year: int, window: int, sex: str = "", level: str = ""):
        s = self.ev["series"].get(f"{metric}|{country}|{sex}|{level}")
        if not s:
            return None
        best = min(s, key=lambda y: (abs(int(y) - year), int(y)))
        if abs(int(best) - year) > window:
            return None
        v, oid, typ = s[best]
        return {"value": float(v), "id": oid, "year": int(best), "type": typ, "distance": abs(int(best) - year)}

    def cpi(self, country: str, year: int):
        c = (self.ev.get("cpi") or {}).get(country) or {}
        v = c.get(str(year))
        return (D(v[0]), v[1]) if v else None

    def fx(self, country: str, year: int, window: int = 1):
        c = (self.ev.get("fx") or {}).get(country) or {}
        for d in range(window + 1):
            for y in (year - d, year + d):
                if str(y) in c:
                    return D(c[str(y)][0]), c[str(y)][1]
        return None

    def assumption(self, domains: set[str], kinds: set[str], year: int, country: str | None = None) -> dict | None:
        for a in self.assumptions:
            pa = a["parsed"]
            if a["domain"] in domains and pa["kind"] in kinds and (a.get("yearStart") is None or a["yearStart"] <= year) \
                    and (a.get("yearEnd") is None or year <= a["yearEnd"]) and (country is None or pa.get("country") in (None, country)):
                return a
        return None

    # ----------------------------------------------------------------- event recording
    def record(self, st: dict, domain: str, event_type: str, explanation: str, *, outcome: str = "DETERMINISTIC", cls: str = "DETERMINISTIC",
               rule: str, importance: int = 2, before=None, after=None, pr: Prob | None = None, draw: float | None = None,
               evidence_ids=(), assumption_ids=(), prior_ids=(), fact_ids=(), lineage: dict | None = None) -> dict:
        e = {"seq": len(self.events), "year": st["year"], "age": st["age"], "domain": domain, "eventType": event_type,
             "stateBefore": before or {}, "stateAfter": after or {}, "probability": None if pr is None else round(pr.final(), 6),
             "baseProbability": None if pr is None else round(pr.base, 6), "probabilityClass": pr.base_class if pr else cls,
             "evidenceIds": list(pr.evidence_ids if pr else evidence_ids), "assumptionIds": list(pr.assumption_ids if pr else assumption_ids),
             "priorIds": list(pr.prior_ids if pr else prior_ids), "factIds": list(pr.fact_ids if pr else fact_ids),
             "modifiers": list(pr.modifiers) if pr else [], "randomDraw": None if draw is None else round(draw, 6), "ruleId": rule, "ruleVersion": "1",
             "outcome": outcome, "occurred": outcome in ("OCCURRED", "FORCED", "DETERMINISTIC", "SCENARIO_OVERRIDE"), "importance": importance,
             "explanation": explanation, "scenarioOverride": outcome == "SCENARIO_OVERRIDE", "lineage": (pr.lineage if pr else None) or lineage}
        e["probabilitySourceIds"] = e["evidenceIds"] + e["assumptionIds"] + e["priorIds"]
        self.events.append(e)
        return e

    def decide(self, st: dict, domain: str, event_type: str, pr: Prob, *, rule: str, what: str, importance: int = 2,
               record_no: bool = False, before=None, after=None) -> bool:
        draw = self.rng(st["year"], f"{domain}:{event_type}").random()
        p = pr.final()
        ok = draw < p
        if ok or (record_no and p >= 0.02):  # rule:R-WHY-NOT-DISPLAY
            self.record(st, domain, event_type, trace_text(pr, draw, ok, what), outcome="OCCURRED" if ok else "NOT_OCCURRED",
                        rule=rule, importance=importance if ok else 1, before=before, after=after if ok else None, pr=pr, draw=draw)
        return ok

    def forced(self, st: dict, domain: str, event_type: str, why: str, *, rule: str, lock_id: str | None = None, override: bool = False,
               before=None, after=None, importance: int = 3) -> dict:
        return self.record(st, domain, event_type, why, outcome="SCENARIO_OVERRIDE" if override else "FORCED", cls="DETERMINISTIC", rule=rule,
                           importance=importance, before=before, after=after, fact_ids=[lock_id] if lock_id else [])

    # ----------------------------------------------------------------- wage reference (never invents; anchors only)
    OCC_GROUPS = (("professional", r"professional|engineer|manager|doctor|teacher|accountant"), ("technician", r"technician|associate|trade|craft"),
                  ("service", r"clerk|service|sales|driver|operator"), ("elementary", r"elementary|labou?r|manual|helper|cleaner"))

    def occ_group(self, text: str) -> str:
        import re
        for g, rx in self.OCC_GROUPS:
            if re.search(rx, text or "", re.I):
                return g
        return "all"

    def ref_wage(self, country: str, year: int, occupation_group: str) -> dict | None:
        cands = []
        for a in self.ev["wageAnchors"]:
            if a["country"] == country and a["years"]:
                v = [D(x) for x in (a.get("low"), a.get("high")) if x not in (None, "")]
                mid = D(a["point"]) if a.get("point") not in (None, "") else (sum(v) / len(v) if v else None)
                if mid is None:
                    continue
                per = (a.get("payPeriod") or "MONTH").upper()
                PP = self.P("P-ACCOUNTING")["payPeriodsPerYear"]
                k = next((D(n) for unit, n in PP.items() if per.startswith(unit)), D(1))
                for y in a["years"]:
                    cands.append({"year": int(y), "annual": mid * k, "low": v[0] * k if len(v) == 2 else None, "high": v[1] * k if len(v) == 2 else None,  # rule:R-RANGE-PAIR
                                  "cls": a["class"], "id": a["id"], "currency": a["currency"], "grossOrNet": a["grossOrNet"], "occ": self.occ_group(a.get("occupation")),
                                  "evidenceIds": a.get("evidenceIds") or [], "factIds": a.get("factIds") or [], "assumptionIds": []})
        for a in self.assumptions:
            pa = a["parsed"]
            if a["domain"] == "income" and pa["kind"] == "AMOUNT" and pa.get("country") == country:
                y0, y1 = a.get("yearStart") or year, a.get("yearEnd") or year
                k = D(self.P("P-ACCOUNTING")["payPeriodsPerYear"]["MONTH"]) if pa["period"] == "MONTH" else D(1)
                for y in range(y0, y1 + 1):
                    cands.append({"year": y, "annual": D(pa["value"]) * k, "low": None, "high": None, "cls": "ASSUMPTION_BASED", "id": a["id"],
                                  "currency": pa["currency"], "grossOrNet": "UNKNOWN", "occ": "all", "evidenceIds": [], "factIds": [], "assumptionIds": [a["id"]]})
        if not cands:
            return None
        c = min(cands, key=lambda x: (abs(x["year"] - year), x["cls"] != "EMPIRICAL", x["year"]))
        val, cls, method, prior_ids, ev_ids = c["annual"], c["cls"], "anchor year", [], list(c["evidenceIds"])
        cov = "ASSUMED" if c["cls"] == "ASSUMPTION_BASED" else "DIRECT" if c["year"] == year else "OUTSIDE_ANCHOR_YEAR"
        chain = [{"step": "anchor", "label": f"{'assumption' if c['cls'] == 'ASSUMPTION_BASED' else 'wage anchor'} {c['id']} ({c['year']}, {c['occ']})",
                  "value": str(q2(val)), "currency": c["currency"], "coverage": cov, "classification": c["cls"],
                  "sourceIds": c["evidenceIds"] + c["assumptionIds"] + c["factIds"]}]
        factor = D(1)
        if c["year"] != year:
            a, b = self.cpi(country, c["year"]), self.cpi(country, year)
            if a and b:
                factor = b[0] / a[0]
                cls = weakest(cls, "DERIVED_FROM_EMPIRICAL")
                method = f"CPI-adjusted from {c['year']} anchor (CPI {a[0]:.2f}→{b[0]:.2f})"
                ev_ids += [a[1], b[1]]
                chain.append({"step": "temporal", "label": f"CPI {c['year']}→{year}", "factor": str(round(factor, 6)), "classification": "DERIVED_FROM_EMPIRICAL",
                              "sourceIds": [a[1], b[1]]})
            else:
                g = D(str(self.P("P-WAGE-NOMINAL-GROWTH")["rate"]))
                factor = (D(1) + g) ** (year - c["year"]) if year >= c["year"] else D(1) / ((D(1) + g) ** (c["year"] - year))
                cls = weakest(cls, "PROVISIONAL_SYSTEM_PRIOR")
                method = f"moved {year - c['year']:+d} years from {c['year']} anchor with nominal-growth prior (no CPI pair)"
                prior_ids.append(self.pid("P-WAGE-NOMINAL-GROWTH"))
                chain.append({"step": "temporal", "label": f"nominal-growth prior {g} /yr over {year - c['year']:+d} years (no CPI pair in snapshot)",
                              "factor": str(round(factor, 6)), "classification": "PROVISIONAL_SYSTEM_PRIOR", "sourceIds": [self.pid("P-WAGE-NOMINAL-GROWTH")]})
        occ = self.P("P-WAGE-OCCUPATION")
        occ_ratio = D(str(occ.get(occupation_group, 1.0))) / D(str(occ.get(c["occ"], 1.0))) if occupation_group != c["occ"] else D(1)
        if occ_ratio != 1:
            prior_ids.append(self.pid("P-WAGE-OCCUPATION"))
            cls = weakest(cls, "PROVISIONAL_SYSTEM_PRIOR")
            chain.append({"step": "occupation", "label": f"occupation ratio {c['occ']}→{occupation_group}", "factor": str(round(occ_ratio, 6)),
                          "classification": "PROVISIONAL_SYSTEM_PRIOR", "sourceIds": [self.pid("P-WAGE-OCCUPATION")]})
        return {"annual": val * factor * occ_ratio, "low": c["low"] * factor * occ_ratio if c["low"] is not None else None,
                "high": c["high"] * factor * occ_ratio if c["high"] is not None else None, "currency": c["currency"], "class": cls, "anchorId": c["id"],
                "anchorYear": c["year"], "method": method + (f"; occupation ratio {occ_ratio:.2f} ({c['occ']}→{occupation_group})" if occ_ratio != 1 else ""),
                "priorIds": prior_ids, "evidenceIds": ev_ids, "assumptionIds": c["assumptionIds"], "factIds": c["factIds"], "grossOrNet": c["grossOrNet"],
                "anchorCoverage": cov, "chain": chain}

    def any_ref_wage(self, country: str, year: int) -> dict | None:
        return self.ref_wage(country, year, "all")


def gompertz_annual(A: float, b: float, age: int) -> float:
    """Annual death probability from hazard A·e^(b·x) integrated over [age, age+1)."""
    H = A * math.exp(b * age) * (math.exp(b) - 1) / b
    return 1 - math.exp(-H)


def gompertz_A_from_q(q: float, b: float, x0: int = 15, x1: int = 60) -> float:  # rule:R-UN-AGE-GROUPS
    H = -math.log(max(1e-9, 1 - q))  # rule:R-NUMERIC-GUARD
    return H * b / (math.exp(b * x1) - math.exp(b * x0))
