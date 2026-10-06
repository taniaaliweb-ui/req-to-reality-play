"""Model inspection: deterministic rules, methodologies, known limitations and the hidden-constant scanner.

Every consequential number used by the simulation lives in the prior registry (priors.py). The few numeric
literals that remain in rule code are NOT model parameters: each is tagged on its line with `# rule:<ID>`
and the ID must be one of DETERMINISTIC_RULES below. `scan_constants()` enforces this (tests + Model Validation)."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from app.simulation import ENGINE_VERSION

DETERMINISTIC_RULES: dict[str, str] = {
    "R-UN-AGE-GROUPS": "Age-group boundaries of the UN WPP broad measures (0, 1–4, 5–14, 15+, Q15–60) and the 1/4 exponent annualising 4q1. Structural, set by the source.",
    "R-PER-THOUSAND": "UN WPP rates are published per 1,000; dividing by 1000 is a unit conversion.",
    "R-PROB-CAP": "Probabilities are clamped to [0, 0.995] so that no stochastic event becomes certain through modifiers (certainty only via locks/overrides).",
    "R-TRAIT-CENTRE": "Trait centring c = 2·trait/100 − 1 maps the 0–100 slider to [−1, 1]; the scale itself is P-CONTROL-SCALING.realismBase.",
    "R-WHY-NOT-DISPLAY": "Which non-occurring draws are kept for 'See why not' (p ≥ 2% or every 5th year). Affects display only, never outcomes.",
    "R-NUMERIC-GUARD": "Numerical guards (log of 1e-9 floor; experience sentinel) that prevent invalid arithmetic. No behavioural effect in valid ranges.",
    "R-MAX-YEARS": "Loop guard: a simulation never runs more than 130 years (death is certain at P-MORT-GOMPERTZ.maxAge before that).",
    "R-LOGNORMAL-MEAN": "Log-normal mean correction −sd²/2 keeps the individual wage factor's expected value at 1 (sd is P-WAGE-SPREAD).",
    "R-PERCENT": "Enrollment ratios are published in percent; dividing by 100 is a unit conversion.",
    "R-SLIDER-NEUTRAL": "Controls and traits default to the neutral slider value 50 when missing; /100 maps 0–100 to 0–1.",
    "R-RANGE-PAIR": "A wage anchor range is exactly two values (low, high).",
    "R-OUTCOME-POSITION": "Summary label 'improved/stable/declined' compares net worth at 30 vs death in subsistence-floor units (±2). Reporting only.",
}

METHODOLOGY = {
    "mortality": [
        "Annual hazards are drawn every simulated year; death age is never set from life expectancy.",
        "PREFERRED: UN WPP 2024 abridged life tables (age-specific nqx by country, single year and sex). Annual q at age x = 1 − (1 − nqx)^(1/n) for the "
        "group [x0, x0+n) containing x (constant hazard within the group); age 0 uses q0 directly; open group 100+ uses 1 − exp(−mx). "
        "Formula MORT-LT-ANNUAL v1; nearest life-table year within P-MORT-LT.maxYearDistance. Projection years (2024+) are labelled DERIVED.",
        "FALLBACK (only when the snapshot has no life table for that country/sex/year): IMR (age 0), Q5 & IMR (1–4), factor × Q5 (5–14), Gompertz with level "
        "solved from Q15–60 and slope prior b (15+). Formula MORT-BROAD v1. Each fallback year is flagged ageSpecificAvailable=false and audited.",
        "Health-state multipliers (P-HEALTH-TRANSITIONS.hazardMultiplier) are applied on top and listed as modifiers.",
        "Every hazard stores lineage: country, year, source year, sex, age, age group, source indicator, source value, observation ids, formula id/version, annual probability.",
    ],
    "wage": [
        "Anchor: nearest approved wage baseline (EMPIRICAL/DERIVED) or explicit income assumption (ASSUMED) in the frozen snapshot. Coverage DIRECT only in the anchor's own year.",
        "Temporal move: CPI ratio if both CPI years are in the snapshot (DERIVED_FROM_EMPIRICAL), else the nominal-growth prior (PROVISIONAL).",
        "Occupation ratio (prior P-WAGE-OCCUPATION) when the simulated occupation differs from the anchor's.",
        "Individual position: uniform within an anchor range, or log-normal around a point (prior P-WAGE-SPREAD) — SIMULATED.",
        "Experience and seniority factors (priors), business and partial-retirement factors (priors).",
        "The final wage is SIMULATED; its classification is the weakest component — it can never look evidence-derived when any step is a prior or assumption.",
        "The full chain (anchor → each adjustment with classification → final) is stored per year (wageProvenance.chain) and on the first-job event.",
    ],
    "financialReconciliation": [
        "Decimal ledgers per currency (cash, investments, property, business, debt, mortgage), 2-decimal rounding.",
        "Each year and currency: opening net worth + income − expenses + gains + transfers = closing net worth; any non-zero difference is an audit error.",
        "Currency conversion only with World Bank annual-average FX observations frozen in the snapshot; otherwise balances stay in their currency.",
        "Shortfalls: sell investments → family support draw → borrowing up to the credit limit (P-ECON-RULES) → unmet needs recorded as deprivation.",
    ],
}

KNOWN_LIMITATIONS = [
    "Most behavioural probabilities (career, relationships, housing, health, outliers) are PROVISIONAL MODEL PRIORS, not estimated from data.",
    "Life tables are national; no regional/urban or socioeconomic mortality differentials are modelled.",
    "Abridged life tables give 5-year age groups; the within-group hazard is assumed constant.",
    "Wage anchors exist only for the years published (e.g. ILOSTAT UAE 2009); other years are moved by CPI or a prior.",
    "Taxes are a flat effective-rate prior; pensions default to 0% replacement unless an assumption is given.",
    "Household spending uses income shares (prior) with a subsistence floor; no consumption survey is used yet.",
    "Historical shocks only affect outcomes once the event is marked verified; effect sizes are priors.",
    "Monte Carlo spreads reflect model randomness, not population distributions.",
]

SCAN_FILES = ["rules/career.py", "rules/education.py", "rules/fertility.py", "rules/health.py", "rules/housing.py", "rules/migration.py",
              "rules/mortality.py", "rules/outliers.py", "rules/relationships.py", "rules/retirement.py", "economics.py", "engine.py", "context.py"]
TRIVIAL = {0, 1, -1, 0.0, 1.0}
TRIVIAL_DEC = {"0", "1", "0.00", "0.01", ""}
SKIP_KW = {"importance", "imp", "record_no", "max_years", "seq"}
TAG = re.compile(r"#\s*rule:([A-Z0-9\-]+)")


def scan_constants(root: Path | None = None) -> dict:
    """Find numeric literals in simulation code that are neither trivial nor tagged with a registered deterministic rule."""
    root = root or Path(__file__).parent
    findings, tagged = [], []
    for rel in SCAN_FILES:
        src = (root / rel).read_text()
        lines = src.splitlines()
        tree = ast.parse(src)
        skip: set[int] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.keyword) and n.arg in SKIP_KW:
                skip |= {id(x) for x in ast.walk(n.value)}
            elif isinstance(n, ast.Subscript):
                skip |= {id(x) for x in ast.walk(n.slice)}
            elif isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) in ("round", "quantize", "range", "enumerate", "zfill", "split", "rsplit"):
                for a in n.args[1:] if getattr(n.func, "id", "") == "round" else n.args:
                    skip |= {id(x) for x in ast.walk(a)}
            elif isinstance(n, ast.FormattedValue) and n.format_spec is not None:
                skip |= {id(x) for x in ast.walk(n.format_spec)}
            elif isinstance(n, (ast.FunctionDef,)):
                for d in n.args.defaults + n.args.kw_defaults:
                    if d is not None:
                        skip |= {id(x) for x in ast.walk(d)}
        for n in ast.walk(tree):
            val = None
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                if n.value in TRIVIAL:
                    continue
                val = n.value
            elif isinstance(n, ast.Call) and getattr(n.func, "id", "") in ("D", "Decimal") and n.args and isinstance(n.args[0], ast.Constant) \
                    and isinstance(n.args[0].value, str):
                if n.args[0].value in TRIVIAL_DEC:
                    continue
                val = f'D("{n.args[0].value}")'
                skip.add(id(n.args[0]))
            else:
                continue
            if id(n) in skip:
                continue
            line = lines[n.lineno - 1]
            m = TAG.search(line)
            if m and m.group(1) in DETERMINISTIC_RULES:
                tagged.append({"file": rel, "line": n.lineno, "value": str(val), "rule": m.group(1)})
            else:
                findings.append({"file": rel, "line": n.lineno, "value": str(val), "code": line.strip()[:160]})
    return {"engineVersion": ENGINE_VERSION, "unregistered": findings, "tagged": tagged, "filesScanned": SCAN_FILES}
