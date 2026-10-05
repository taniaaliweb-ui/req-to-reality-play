"""Deterministic economic calculations. Pure functions — no database, no network, no LLM.

Precision: all arithmetic uses Python Decimal with 28 significant digits (decimal.getcontext
default, set explicitly below). Results are stored unrounded as decimal strings; rounding to
2 decimal places (ROUND_HALF_EVEN) happens only in `display`, for presentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation

ENGINE_VERSION = "1.0"
INFLATION_FORMULA = "inflation-adjust-v1"
FX_FORMULA = "fx-usd-bridge-annual-avg-v1"
ANNUALIZE_FORMULA = "wage-annualize-v1"
CTX = Context(prec=28)


@dataclass
class EngineResult:
    status: str  # OK | MISSING_DATA | INVALID_INPUT
    calculation_type: str
    formula: str
    formula_version: str
    engine_version: str = ENGINE_VERSION
    result: str | None = None
    display: str | None = None
    parameters: dict = field(default_factory=dict)
    inputs: list[dict] = field(default_factory=list)  # [{role, value, ...}]
    missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status, "calculationType": self.calculation_type, "formula": self.formula,
            "formulaVersion": self.formula_version, "engineVersion": self.engine_version, "result": self.result,
            "display": self.display, "parameters": self.parameters, "inputs": self.inputs, "missing": self.missing,
            "errors": self.errors, "labels": self.labels,
        }


def D(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        x = repr(x)
    try:
        return Decimal(str(x))
    except InvalidOperation as e:
        raise ValueError(f"not a number: {x!r}") from e


def display(x: Decimal, places: int = 2) -> str:
    return str(x.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN))


def adjust_for_inflation(amount, source_year: int, target_year: int, source_cpi, target_cpi, *, country: str, currency: str) -> EngineResult:
    """real_amount = nominal_amount × CPI(target_year) ÷ CPI(source_year), same country only."""
    r = EngineResult("OK", "inflation-adjust", "amount × CPI_target ÷ CPI_source", INFLATION_FORMULA,
                     parameters={"amount": str(amount), "sourceYear": source_year, "targetYear": target_year, "country": country, "currency": currency},
                     labels=[f"{currency} of {source_year} expressed in {target_year} {currency} (inflation-adjusted, same country)"])
    if source_cpi is None:
        r.missing.append(f"CPI {country} {source_year}")
    if target_cpi is None:
        r.missing.append(f"CPI {country} {target_year}")
    if r.missing:
        r.status = "MISSING_DATA"
        return r
    try:
        a, s, t = D(amount), D(source_cpi), D(target_cpi)
    except ValueError as e:
        r.status, r.errors = "INVALID_INPUT", [str(e)]
        return r
    if s <= 0 or t <= 0:
        r.status, r.errors = "INVALID_INPUT", ["CPI values must be positive"]
        return r
    res = CTX.divide(CTX.multiply(a, t), s)
    r.result, r.display = str(res), display(res)
    r.inputs = [
        {"role": "nominal_amount", "value": str(a)},
        {"role": "source_cpi", "value": str(s), "year": source_year},
        {"role": "target_cpi", "value": str(t), "year": target_year},
    ]
    return r


def convert_historical_currency(amount, year: int, source_currency: str, target_currency: str, source_lcu_per_usd, target_lcu_per_usd) -> EngineResult:
    """USD = amount ÷ source_LCU_per_USD; target = USD × target_LCU_per_USD (USD bridge, annual averages)."""
    r = EngineResult("OK", "currency-convert", "(amount ÷ source_LCU_per_USD) × target_LCU_per_USD", FX_FORMULA,
                     parameters={"amount": str(amount), "year": year, "sourceCurrency": source_currency, "targetCurrency": target_currency},
                     labels=[f"Historical annual-average conversion ({year}). Not an exact daily rate."])
    if source_currency != "USD" and source_lcu_per_usd is None:
        r.missing.append(f"FX {source_currency} per USD {year}")
    if target_currency != "USD" and target_lcu_per_usd is None:
        r.missing.append(f"FX {target_currency} per USD {year}")
    if r.missing:
        r.status = "MISSING_DATA"
        return r
    try:
        a = D(amount)
        s = Decimal(1) if source_currency == "USD" else D(source_lcu_per_usd)
        t = Decimal(1) if target_currency == "USD" else D(target_lcu_per_usd)
    except ValueError as e:
        r.status, r.errors = "INVALID_INPUT", [str(e)]
        return r
    if s <= 0 or t <= 0:
        r.status, r.errors = "INVALID_INPUT", ["Exchange rates must be positive"]
        return r
    usd = CTX.divide(a, s)
    res = CTX.multiply(usd, t)
    r.result, r.display = str(res), display(res)
    r.parameters["usdIntermediate"] = str(usd)
    r.inputs = [{"role": "nominal_amount", "value": str(a)}]
    if source_currency != "USD":
        r.inputs.append({"role": "source_fx", "value": str(s), "year": year})
    if target_currency != "USD":
        r.inputs.append({"role": "target_fx", "value": str(t), "year": year})
    return r


def calculate_real_income(nominal_income, income_year: int, base_year: int, cpi_income_year, cpi_base_year, *, country: str, currency: str) -> EngineResult:
    """Income of `income_year` in `base_year` prices — same formula as inflation adjustment."""
    r = adjust_for_inflation(nominal_income, income_year, base_year, cpi_income_year, cpi_base_year, country=country, currency=currency)
    r.calculation_type = "real-income"
    return r


ANNUALIZE_REQUIRES = {"MONTHLY": ("monthsPerYear",), "WEEKLY": ("weeksPerYear",), "DAILY": ("daysPerYear",), "HOURLY": ("hoursPerWeek", "weeksPerYear"), "ANNUAL": ()}


def annualize_wage(amount, pay_period: str, assumptions: dict) -> EngineResult:
    """annual = amount × explicit working-time assumptions. Nothing is assumed silently
    (no default 12 months, 40 hours or 52 weeks): each factor must be supplied and is recorded."""
    pp = (pay_period or "").upper()
    need = ANNUALIZE_REQUIRES.get(pp)
    r = EngineResult("OK", "wage-annualize", f"amount × {' × '.join(need) if need else '1'}", ANNUALIZE_FORMULA,
                     parameters={"amount": str(amount), "payPeriod": pp, "assumptions": dict(assumptions)},
                     labels=["Gross/net status unchanged by annualization", "Working-time factors are explicit assumptions"])
    if need is None:
        r.status, r.errors = "INVALID_INPUT", [f"Unknown pay period {pay_period!r}"]
        return r
    try:
        value = D(amount)
        factors = []
        for k in need:
            if assumptions.get(k) in (None, ""):
                r.missing.append(f"Assumption '{k}' is required to annualize a {pp.lower()} wage")
                continue
            f = D(assumptions[k])
            if f <= 0:
                raise ValueError(f"{k} must be positive")
            factors.append(f)
    except ValueError as e:
        r.status, r.errors = "INVALID_INPUT", [str(e)]
        return r
    if r.missing:
        r.status = "MISSING_DATA"
        return r
    out = value
    for f in factors:
        out = CTX.multiply(out, f)
    r.result, r.display = str(out), display(out)
    r.inputs = [{"role": k, "value": str(assumptions[k]), "kind": "assumption"} for k in need]
    return r


def recompute(calculation_type: str, parameters: dict, inputs: dict[str, str]) -> EngineResult:
    """Re-run a stored calculation from its stored parameters + input values (reproducibility check)."""
    if calculation_type in ("inflation-adjust", "real-income"):
        return adjust_for_inflation(inputs["nominal_amount"], parameters["sourceYear"], parameters["targetYear"], inputs.get("source_cpi"), inputs.get("target_cpi"),
                                    country=parameters["country"], currency=parameters["currency"])
    if calculation_type == "currency-convert":
        return convert_historical_currency(inputs["nominal_amount"], parameters["year"], parameters["sourceCurrency"], parameters["targetCurrency"],
                                           inputs.get("source_fx"), inputs.get("target_fx"))
    if calculation_type == "wage-annualize":
        return annualize_wage(parameters["amount"], parameters["payPeriod"], parameters.get("assumptions", {}))
    raise ValueError(f"unknown calculation type {calculation_type}")
