"""Simulation Prior Registry.

A provisional system prior is NOT a researched probability — it is a visible, editable, versioned model
parameter used only where the frozen snapshot has no evidence and the user has not supplied an
assumption. No default probability is hidden inside rule code: every rule reads its parameters from here.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m

LABEL = "Provisional model prior — not externally validated"
CLASSIFICATIONS = ["EMPIRICAL", "DERIVED", "USER_ASSUMPTION", "PROVISIONAL_MODEL_PRIOR", "DETERMINISTIC_ACCOUNTING_RULE"]
CLASS_LABEL = {"PROVISIONAL_MODEL_PRIOR": LABEL, "DERIVED": "Derived method — transforms empirical evidence with a documented formula",
               "DETERMINISTIC_ACCOUNTING_RULE": "Deterministic accounting rule / convention — not a probability",
               "EMPIRICAL": "Empirical — taken from snapshot evidence", "USER_ASSUMPTION": "User assumption"}
# key → (classification, units, provenance). Anything not listed is a PROVISIONAL_MODEL_PRIOR with provenance "LifeSpan model default".
META: dict[str, tuple[str, dict, str]] = {
    "P-MORT-LT": ("DERIVED", {"maxYearDistance": "years"}, "UN WPP 2024 abridged life tables; formula MORT-LT-ANNUAL v1"),
    "P-MORT-GOMPERTZ": ("PROVISIONAL_MODEL_PRIOR", {"b": "per year of age", "maxAnnualHazard": "probability/yr", "maxAge": "years"},
                        "Broad-measure fallback only (used when no life table is in the snapshot); level from UN WPP Q15–60"),
    "P-ACCOUNTING": ("DETERMINISTIC_ACCOUNTING_RULE", {"payPeriodsPerYear": "periods/yr", "equivalenceExtraMember": "adult-equivalents"},
                     "Accounting convention (OECD-modified-style equivalence)"),
    "P-EDU-DURATION": ("DETERMINISTIC_ACCOUNTING_RULE", {"startAge": "years", "primary": "years", "secondary": "years", "tertiary": "years"},
                       "School-system convention (not country evidence)"),
    "P-EVIDENCE-WINDOWS": ("PROVISIONAL_MODEL_PRIOR", {"*": "years"}, "LifeSpan model default"),
    "P-AGE-BOUNDS": ("PROVISIONAL_MODEL_PRIOR", {"*": "years of age"}, "LifeSpan model default"),
    "P-TRAIT-EFFECTS": ("PROVISIONAL_MODEL_PRIOR", {"*": "probability points per centred trait unit"}, "LifeSpan model default"),
    "P-CONTROL-SCALING": ("PROVISIONAL_MODEL_PRIOR", {"*": "multiplier"}, "LifeSpan model design"),
}
DEFAULT_UNITS = {"p": "probability/yr", "rate": "per year", "share": "share of income", "factor": "multiplier"}


def meta(key: str) -> tuple[str, dict, str]:
    return META.get(key, ("PROVISIONAL_MODEL_PRIOR", {}, "LifeSpan model default — not externally validated"))


def defaults() -> dict[str, dict]:
    """Code defaults by key. Frozen inputs created before a prior existed fall back to these (legacy-identical values)."""
    return {k: {"key": k, "id": f"{k}@default", "parameter": param, "enabled": True} for k, _d, _n, _de, param, _c, _no in DEFAULT_PRIORS}

# key, domain, name, description, parameter, conditions, notes
DEFAULT_PRIORS: list[tuple[str, str, str, str, dict, dict, str]] = [
    # ---- mortality / health
    ("P-MORT-GOMPERTZ", "mortality", "Adult mortality age gradient (Gompertz slope)",
     "Shape used to distribute an empirical 15–60 mortality probability (UN WPP Q1560) across single ages and to extend it past 60. "
     "The level comes from evidence; only the slope is a prior.", {"b": 0.085, "maxAnnualHazard": 0.6, "maxAge": 110}, {"ages": "15+"},
     "Gompertz slopes near 0.08–0.10 are common in demographic literature; not validated for this population."),
    ("P-MORT-CHILD-5-14", "mortality", "Ages 5–14 hazard relative to under-five mortality",
     "Annual hazard at ages 5–14 = factor × (Q5 / 1000). Evidence gives Q5; the ratio is a prior.", {"factor": 0.02}, {"ages": "5-14"}, ""),
    ("P-MORT-FALLBACK", "mortality", "Fallback mortality schedule (no evidence)",
     "Used only when the snapshot has no mortality evidence near the year. Gompertz A·e^(b·age) plus infant hazard.",
     {"A": 0.0004, "b": 0.085, "infant": 0.06, "child": 0.01}, {}, "Blocks nothing by itself; counted as prior dependency."),
    ("P-HEALTH-TRANSITIONS", "health", "Lightweight health-state transitions",
     "Annual onset probabilities rise exponentially with age. Not a medical model.",
     {"minorBase": 0.03, "chronicBase": 0.003, "chronicSlope": 0.06, "majorBase": 0.0008, "majorSlope": 0.075, "disabledFromMajor": 0.12,
      "terminalFromMajor": 0.06, "recoverMinor": 0.6, "recoverMajor": 0.25,
      "hazardMultiplier": {"good": 1.0, "minor_condition": 1.1, "chronic_condition": 1.7, "major_condition": 3.0, "disabled": 2.2, "terminal": 30.0},
      "healthcareShare": {"good": 0.02, "minor_condition": 0.03, "chronic_condition": 0.06, "major_condition": 0.12, "disabled": 0.08, "terminal": 0.15}},
     {"ages": "15+"}, ""),
    # ---- education
    ("P-EDU-ENROL", "education", "School enrollment fallback",
     "Used only when no enrollment-ratio evidence exists near the year.", {"primary": 0.8, "secondaryGivenPrimary": 0.55, "tertiaryGivenSecondary": 0.15,
      "classModifier": {"poverty": -0.15, "working": -0.05, "lower-middle": 0.0, "middle": 0.05, "upper-middle": 0.1, "wealthy": 0.15}}, {}, ""),
    ("P-EDU-DROPOUT", "education", "Annual school dropout", "Annual dropout hazard while enrolled.", {"primary": 0.02, "secondary": 0.04, "tertiary": 0.05}, {}, ""),
    ("P-EDU-VOCATIONAL", "education", "Vocational track share", "Share of secondary completers not entering university who take vocational training.",
     {"p": 0.2, "years": 2}, {}, ""),
    ("P-EDU-DURATION", "education", "Education stage durations", "Years per level (system convention, not evidence).",
     {"startAge": 6, "primary": 5, "secondary": 7, "tertiary": 4}, {}, ""),
    # ---- career
    ("P-CAREER-FIRST-JOB", "career", "Annual chance of finding a first job", "After leaving education, from age 14.", {"p": 0.5, "minAge": 14}, {}, ""),
    ("P-CAREER-JOB-LOSS", "career", "Annual job loss", "Base hazard for employees.", {"p": 0.035}, {}, ""),
    ("P-CAREER-REEMPLOY", "career", "Annual re-employment", "Chance an unemployed person finds work in a year.", {"p": 0.5}, {}, ""),
    ("P-CAREER-PROMOTION", "career", "Annual promotion", "Each promotion raises seniority by one.", {"p": 0.07, "raise": 0.08, "maxSeniority": 6}, {}, ""),
    ("P-CAREER-JOB-CHANGE", "career", "Annual voluntary job change", "Small raise on change.", {"p": 0.06, "raise": 0.04}, {}, ""),
    ("P-CAREER-BUSINESS", "career", "Business start / outcome", "Start requires savings ≥ minSavingsYears × annual income.",
     {"start": 0.01, "minSavingsYears": 0.5, "capitalShare": 0.5, "failAnnual": 0.15, "successAnnual": 0.05, "successIncomeMultiplier": 1.8,
      "failIncomeMultiplier": 0.6, "selfEmployedIncomeFactor": 0.9}, {}, ""),
    # ---- wages
    ("P-WAGE-NOMINAL-GROWTH", "income", "Nominal wage drift when CPI is missing",
     "Annual nominal change applied to move a wage anchor to another year when no CPI evidence exists for both years.", {"rate": 0.05}, {}, ""),
    ("P-WAGE-EXPERIENCE", "income", "Experience premium",
     "Real growth per year of experience relative to the anchor's population (assumed average experience).",
     {"rate": 0.02, "plateauYears": 25, "anchorAverageExperience": 12}, {}, ""),
    ("P-WAGE-SPREAD", "income", "Individual position around a point estimate",
     "Log-normal individual factor around a POINT anchor (sd scaled by the randomness control). A RANGE anchor uses a uniform position instead.",
     {"sd": 0.2}, {}, "The chosen value is SIMULATED, not factual."),
    ("P-WAGE-OCCUPATION", "income", "Occupation relative to anchor occupation",
     "Multiplier when the simulated occupation group differs from the anchor's (education-implied).",
     {"elementary": 0.6, "service": 0.8, "technician": 1.0, "professional": 1.5}, {}, ""),
    ("P-TAX-EFFECTIVE", "income", "Effective income tax on gross pay",
     "Applied only when the anchor is GROSS or UNKNOWN (gross/net unknown is reported, not hidden).", {"byCountry": {"ARE": 0.0}, "default": 0.05}, {}, ""),
    # ---- relationships / fertility
    ("P-REL-MEET", "relationships", "Annual chance of a new partnership", "Ages 18–60; declines after 35.", {"p": 0.12, "minAge": 18, "declineAfter": 35, "declineRate": 0.08}, {}, ""),
    ("P-REL-MARRY", "relationships", "Annual marriage while partnered", "", {"p": 0.35}, {}, ""),
    ("P-REL-SEPARATE", "relationships", "Annual separation", "Married or partnered.", {"p": 0.012, "divorceGivenSeparation": 0.6}, {}, ""),
    ("P-REL-PARTNER-WORK", "relationships", "Partner employment", "A partner is NOT assumed to work: drawn once at partnership.",
     {"p": 0.4, "incomeRatio": 0.6}, {}, ""),
    ("P-FERT-SHAPE", "fertility", "Fertility timing shape",
     "Annual birth probability = TFR / fertileYears × parityDecay^children (evidence TFR; shape is a prior).",
     {"fertileYears": 22, "minAge": 18, "maxAge": 45, "parityDecay": 0.75, "unpartneredFactor": 0.05}, {}, ""),
    ("P-FERT-FALLBACK", "fertility", "Fertility fallback (no TFR evidence)", "", {"annual": 0.08}, {}, ""),
    # ---- migration
    ("P-MIG-OPPORTUNITY", "migration", "Annual migration opportunity",
     "Population migration figures are context, not individual probabilities. Base rate with an evidenced migration path vs without.",
     {"withPath": 0.03, "withoutPath": 0.0, "minAge": 18, "maxAge": 55, "failure": 0.15, "returnAnnual": 0.03, "employerHousing": 0.3,
      "remittanceShare": 0.15}, {}, "Without a destination in the evidence/timeline no migration can be simulated."),
    # ---- housing / spending
    ("P-HOUSING", "housing", "Housing transitions and costs",
     "Cost shares of household income by tenure; purchase requires a down payment.",
     {"leaveHome": 0.2, "costShare": {"family_home": 0.0, "shared": 0.12, "rent": 0.25, "employer_housing": 0.03, "owned": 0.05, "mortgaged": 0.05},
      "purchase": 0.06, "priceToIncome": 5.0, "downPayment": 0.2, "mortgageRate": 0.09, "mortgageYears": 20, "appreciationNoCpi": 0.04}, {}, ""),
    ("P-SPEND", "household_spending", "Household spending shares",
     "Shares of household income, with a subsistence floor in units of the reference wage (equivalised household size).",
     {"food": 0.25, "utilities": 0.06, "transport": 0.07, "other": 0.15, "childShare": 0.07, "childEducationShare": 0.05,
      "floorOfReferenceWage": 0.35, "discretionaryCutMax": 0.6}, {}, ""),
    ("P-FINANCE", "household_spending", "Savings, debt and returns",
     "Investment allocation, returns and borrowing terms.",
     {"cashRate": 0.02, "investShare": 0.4, "investReturn": 0.05, "investVol": 0.12, "debtRate": 0.14, "debtRepay": 0.2,
      "distressDebtToIncome": 3.0, "familySupport": 0.4}, {}, ""),
    # ---- retirement
    ("P-RET", "retirement", "Retirement timing and pension",
     "Pension rules are missing: replacement rate 0 unless an assumption says otherwise.",
     {"earliest": 55, "hazard": {"55": 0.08, "58": 0.15, "60": 0.35, "62": 0.3, "65": 0.6, "70": 0.8}, "replacement": 0.0, "returnToWork": 0.03}, {}, ""),
    # ---- outliers & shocks
    ("P-OUTLIER", "outliers", "Rare outcomes",
     "Annual probabilities, scaled by the outlier-intensity control. At most one outlier per year.",
     {"windfall": 0.004, "breakthrough": 0.004, "inheritance": 0.003, "assetLoss": 0.004, "windfallYears": 1.0, "inheritanceYears": 2.0,
      "breakthroughMultiplier": 1.3, "assetLossShare": 0.35}, {}, ""),
    ("P-SHOCK-EFFECTS", "historical", "Effects of VERIFIED historical events",
     "Only events marked verified affect the simulation. Unverified events are listed as research gaps.",
     {"financial-crisis": {"jobLoss": 2.0, "investReturn": -0.25}, "oil-shock": {"jobLoss": 1.4, "investReturn": -0.1},
      "currency-crisis": {"jobLoss": 1.5, "investReturn": -0.15}, "pandemic": {"jobLoss": 1.8, "investReturn": -0.05, "migration": 0.3},
      "war": {"jobLoss": 1.8, "migration": 0.5}, "natural-disaster": {"assetLoss": 0.05}, "policy-change": {}}, {}, ""),
    # ---- Phase 6.1: every consequential constant formerly inside rule code
    ("P-MORT-LT", "mortality", "Age-specific mortality from life tables (method)",
     "Annual death probability at age x = 1 − (1 − nqx)^(1/n) for the UN WPP abridged age group containing x (constant hazard within the group); "
     "open group 100+: 1 − exp(−mx). Uses the life-table year nearest the simulated year within maxYearDistance.",
     {"maxYearDistance": 2}, {"ages": "all"}, "Formula MORT-LT-ANNUAL v1. The only parameter is the year tolerance."),
    ("P-EVIDENCE-WINDOWS", "evidence", "Nearest-year tolerance for evidence lookups",
     "How far (years) a rule may look from the simulated year for a population statistic before treating it as missing.",
     {"mortalityBroad": 2, "enrollment": 3, "fertility": 2, "fx": 1, "migrationPathYears": 5}, {}, "Beyond the window the statistic is MISSING (never interpolated)."),
    ("P-TRAIT-EFFECTS", "traits", "Character trait effects",
     "Additive probability points per centred trait c = 2·trait/100 − 1 (scaled by realism). Multiplicative/allocation effects are noted per key.",
     {"firstJob": {"aptitude": 0.05, "socialSkills": 0.05}, "reemploy": {"socialSkills": 0.08, "resilience": 0.06}, "businessSuccess": {"aptitude": 0.01},
      "jobLoss": {"discipline": -0.012}, "businessStart": {"riskTolerance": 0.012, "ambition": 0.008}, "promotion": {"ambition": 0.04, "aptitude": 0.03},
      "primaryEntry": {"aptitude": 0.08}, "secondaryEntry": {"aptitude": 0.08}, "tertiaryEntry": {"aptitude": 0.15, "ambition": 0.06},
      "dropout": {"discipline": -0.02}, "birth": {"familyAttachment": 0.01}, "healthRecovery": {"resilience": 0.1},
      "homePurchase": {"financialDiscipline": 0.03}, "returnMigration": {"familyAttachment": 0.03},
      "migration": {"migrationWillingness": 0.025, "familyAttachment": -0.015}, "newPartnership": {"socialSkills": 0.04},
      "familySupport": {"familyAttachment": 0.1}, "investShare": {"riskTolerance": 0.15}, "discretionarySpending": {"financialDiscipline": -0.15},
      "remittanceShare": {"familyAttachment": 0.5}}, {}, "investShare / discretionarySpending / remittanceShare are allocation effects, not probabilities."),
    ("P-STATE-MODIFIERS", "state", "Life-state modifiers",
     "Effects of the simulated state (distress, unemployment, marriage, health, business history) on other transitions.",
     {"reemployWageFactor": 0.95, "businessRevalueMultiplier": 2.0, "businessFailAfterSuccessFactor": 0.4, "dropoutDistressMultiplier": 1.5,
      "tertiaryEntryDistressMultiplier": 0.6, "cohabitingFertilityMultiplier": 0.6, "distressFertilityMultiplier": 0.7, "separationDistressMultiplier": 1.5,
      "leaveHomeMarriedAdd": 0.3, "migrateUnemployedAdd": 0.02, "returnUnemployedAbroadAdd": 0.1, "wageOpportunityMinRatio": 1.5,
      "wageOpportunityPerRatio": 0.006, "wageOpportunityCap": 0.03, "migrationFailureCostYears": 0.25, "retireMajorHealthAdd": 0.2,
      "retireChronicHealthAdd": 0.05, "retireUnemployedAdd": 0.15, "healthProgressionMultiplier": 3.0, "enrollmentCap": 0.98, "maxMigrations": 2}, {}, ""),
    ("P-AGE-BOUNDS", "ages", "Age bounds used by rules",
     "Ages at which rules start/stop applying. Conventions, not evidence.",
     {"adulthood": 18, "healthModelMinAge": 15, "healthReferenceAge": 30, "purchaseMinAge": 25, "purchaseMaxAge": 65, "businessMinAge": 25,
      "businessMaxAge": 60, "partnershipMaxAge": 60, "partnerMinAge": 16, "partnerAgeOffsetMin": -4, "partnerAgeOffsetMax": 3, "inheritanceMinAge": 30,
      "inheritanceMaxAge": 65, "retirementCapAge": 75, "returnToWorkMaxAge": 70, "partnerWorksUntilAge": 62, "childDependentUntilAge": 22,
      "childSchoolStartAge": 6, "childSchoolEndAge": 21, "lockedFirstJobMinAge": 12}, {}, ""),
    ("P-ECON-RULES", "household_spending", "Household economics rules",
     "Spending split, partial retirement, shortfall handling, credit limit and savings allocation.",
     {"partialRetirementIncomeFactor": 0.5, "assumedSpendingSplit": {"food": 0.45, "utilities": 0.12, "transport": 0.13, "other": 0.3},
      "foodScaleExtraMember": 0.25, "defaultHealthcareShare": 0.02, "familySupportCoverShare": 0.5, "creditLimitMultipleOfDistress": 1.2,
      "cashBufferShareOfExpenses": 0.5, "investShareMax": 0.9, "assetLossShockScale": 20.0,
      "forcedSaleAfterDistressYears": 3, "distressExitFraction": 0.5}, {},
     "assumedSpendingSplit applies only when a spending ASSUMPTION gives a total."),
    ("P-CONTROL-SCALING", "controls", "Scenario control scaling",
     "Control value v ∈ [0,1] (slider/100) → multiplier neutralOffset + v; outlier intensity → outlierBase + outlierSlope·v; trait scale = realismBase − realism/100.",
     {"neutralOffset": 0.5, "outlierBase": 0.25, "outlierSlope": 1.5, "realismBase": 1.5}, {}, "At the default slider (50) every multiplier is 1.0."),
    ("P-ACCOUNTING", "accounting", "Accounting conventions",
     "Pay-period annualisation and household equivalence scale (OECD-modified style: 1 + 0.5 per additional member). Deterministic, not probabilities.",
     {"payPeriodsPerYear": {"MONTH": 12, "WEEK": 52, "DAY": 260, "HOUR": 2080}, "equivalenceExtraMember": 0.5}, {},
     "DAY assumes 260 working days; HOUR assumes 2,080 hours (40 h × 52 weeks)."),
]


def registry_version(priors: list[dict]) -> str:
    return hashlib.sha256(json.dumps(sorted((p["id"], p["parameter"], p["enabled"]) for p in priors), sort_keys=True, default=str).encode()).hexdigest()[:16]


def prior_out(p: m.SimulationPrior) -> dict:
    return {"id": p.id, "key": p.key, "version": p.version, "domain": p.domain, "name": p.name, "description": p.description, "parameter": p.parameter,
            "conditions": p.conditions, "sourceType": p.source_type, "notes": p.notes, "enabled": p.enabled, "active": p.active,
            "classification": meta(p.key)[0], "units": meta(p.key)[1], "provenance": meta(p.key)[2], "label": CLASS_LABEL[meta(p.key)[0]], "createdAt": p.created_at, "updatedAt": p.updated_at}


def seed_priors(db: Session, ts: str) -> None:
    have = {k for (k,) in db.execute(select(m.SimulationPrior.key))}
    for key, dom, name, desc, param, cond, notes in DEFAULT_PRIORS:
        if key not in have:
            db.add(m.SimulationPrior(id=f"{key}@v1", key=key, version=1, domain=dom, name=name, description=desc, parameter=param, conditions=cond,
                                     notes=notes, enabled=True, active=True, created_at=ts, updated_at=ts))
    db.commit()


def active(db: Session) -> list[m.SimulationPrior]:
    return list(db.scalars(select(m.SimulationPrior).where(m.SimulationPrior.active.is_(True)).order_by(m.SimulationPrior.domain, m.SimulationPrior.key)))


def update(db: Session, key: str, ts: str, *, parameter: dict | None = None, enabled: bool | None = None, notes: str | None = None,
           description: str | None = None) -> m.SimulationPrior:
    """Edits never mutate a prior in place: they create version n+1 so frozen inputs stay reproducible."""
    cur = db.scalar(select(m.SimulationPrior).where(m.SimulationPrior.key == key, m.SimulationPrior.active.is_(True)))
    if cur is None:
        raise LookupError(key)
    if parameter is not None and set(parameter) != set(cur.parameter):
        raise ValueError("Parameter keys must match the prior definition: " + ", ".join(sorted(cur.parameter)))
    new = m.SimulationPrior(id=f"{key}@v{cur.version + 1}", key=key, version=cur.version + 1, domain=cur.domain, name=cur.name,
                            description=description if description is not None else cur.description,
                            parameter=parameter if parameter is not None else cur.parameter, conditions=cur.conditions,
                            notes=notes if notes is not None else cur.notes, enabled=cur.enabled if enabled is None else enabled,
                            active=True, created_at=ts, updated_at=ts)
    cur.active = False
    cur.updated_at = ts
    db.add(new)
    db.commit()
    return new


def history(db: Session, key: str) -> list[m.SimulationPrior]:
    return list(db.scalars(select(m.SimulationPrior).where(m.SimulationPrior.key == key).order_by(m.SimulationPrior.version.desc())))
