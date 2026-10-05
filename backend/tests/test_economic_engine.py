"""Pure deterministic calculation tests — no network, no database."""
from decimal import Decimal

from app.services import economic_engine as eng


def test_inflation_basic():
    r = eng.adjust_for_inflation(100, 1990, 2000, 50, 100, country="XXX", currency="LCU")
    assert r.status == "OK" and Decimal(r.result) == Decimal(200)
    assert r.formula_version == "inflation-adjust-v1" and r.engine_version == "1.0"
    assert {i["role"] for i in r.inputs} == {"nominal_amount", "source_cpi", "target_cpi"}


def test_inflation_reverse_period():
    r = eng.adjust_for_inflation(200, 2000, 1990, 100, 50, country="XXX", currency="LCU")
    assert Decimal(r.result) == Decimal(100)


def test_inflation_decimal_precision():
    # Real World Bank values: India CPI 1995 = 37.7452131691141, 2010 = 100
    r = eng.adjust_for_inflation("100000", 1995, 2010, "37.7452131691141", "100", country="IND", currency="INR")
    assert r.result.startswith("264934.256833995")  # 100000*100/37.7452131691141
    assert r.display == "264934.26"
    # Full precision kept, not rounded
    assert len(r.result.replace(".", "")) > 15


def test_inflation_zero_and_invalid_cpi_rejected():
    assert eng.adjust_for_inflation(100, 1990, 2000, 0, 100, country="X", currency="L").status == "INVALID_INPUT"
    assert eng.adjust_for_inflation(100, 1990, 2000, -5, 100, country="X", currency="L").status == "INVALID_INPUT"
    assert eng.adjust_for_inflation("abc", 1990, 2000, 50, 100, country="X", currency="L").status == "INVALID_INPUT"


def test_inflation_missing_cpi_never_invented():
    r = eng.adjust_for_inflation(100, 1990, 2000, None, 100, country="ARE", currency="AED")
    assert r.status == "MISSING_DATA" and r.result is None and r.missing == ["CPI ARE 1990"]


def test_fx_to_usd():
    r = eng.convert_historical_currency(500, 1998, "AAA", "USD", 50, None)
    assert r.status == "OK" and Decimal(r.result) == Decimal(10)
    assert "annual-average" in r.labels[0]


def test_fx_cross_currency_usd_bridge():
    r = eng.convert_historical_currency(500, 1998, "AAA", "BBB", 50, 2)
    assert Decimal(r.parameters["usdIntermediate"]) == Decimal(10)
    assert Decimal(r.result) == Decimal(20)
    assert [i["role"] for i in r.inputs] == ["nominal_amount", "source_fx", "target_fx"]


def test_fx_missing_rate():
    r = eng.convert_historical_currency(500, 1998, "AAA", "BBB", 50, None)
    assert r.status == "MISSING_DATA" and r.missing == ["FX BBB per USD 1998"]


def test_recompute_reproduces():
    r = eng.adjust_for_inflation(100, 1990, 2000, "37.5", "81.25", country="X", currency="L")
    again = eng.recompute("inflation-adjust", r.parameters, {"nominal_amount": "100", "source_cpi": "37.5", "target_cpi": "81.25"})
    assert again.result == r.result
