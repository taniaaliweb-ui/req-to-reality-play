"""Truth pipeline: provider observations → local store → Fact Ledger → deterministic calculation
→ derived Fact + lineage. Routers call these functions; calculations live in economic_engine."""
from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.providers.base import Observation, ProviderError
from app.services import economic_engine as eng
from app.services.repository import now_iso

CPI = "FP.CPI.TOTL"
FX = "PA.NUS.FCRF"
# ISO3 → ISO 4217 for currencies the demo needs; other currencies are passed explicitly.
CURRENCY_BY_COUNTRY = {"IND": "INR", "ARE": "AED", "USA": "USD", "GBR": "GBP", "PAK": "PKR", "BGD": "BDT", "NPL": "NPR", "LKA": "LKR", "PHL": "PHP", "SAU": "SAR"}
ISO2_TO_3 = {"IN": "IND", "AE": "ARE", "US": "USA", "GB": "GBR", "PK": "PAK", "BD": "BGD", "NP": "NPL", "LK": "LKA", "PH": "PHL", "SA": "SAU"}
COUNTRY_BY_CURRENCY = {v: k for k, v in CURRENCY_BY_COUNTRY.items()}
SOURCE_IDS = {"world-bank": "SRC-WB-WDI"}


def obs_id(provider: str, indicator: str, country: str, year: int) -> str:
    return f"{provider}:{indicator}:{country.upper()}:{year}"


# ---------- observations ----------
def store_observations(db: Session, observations: list[Observation]) -> dict:
    """Insert new, leave identical values alone (but record the new retrieval time), and keep a
    revision row whenever a refreshed value differs."""
    ts = now_iso()
    created = unchanged = revised = 0
    for o in observations:
        oid = obs_id(o.provider, o.indicator_code, o.country_code, o.year)
        row = db.get(m.ExternalObservation, oid)
        val = str(o.value)
        if row is None:
            db.add(m.ExternalObservation(
                id=oid, provider=o.provider, dataset=o.dataset, indicator_code=o.indicator_code, indicator_name=o.indicator_name,
                country_code=o.country_code.upper(), country_name=o.country_name, year=o.year, value=val, unit=o.unit,
                source_organization=o.source_organization, source_note=o.source_note, license=o.license, source_url=o.source_url,
                provider_last_updated=o.provider_last_updated, raw_metadata=o.raw, retrieved_at=ts, created_at=ts, updated_at=ts))
            created += 1
            continue
        if Decimal(row.value) == o.value:
            unchanged += 1
        else:
            db.add(m.ObservationRevision(observation_id=oid, old_value=row.value, new_value=val, old_retrieved_at=row.retrieved_at,
                                         new_retrieved_at=ts, old_provider_last_updated=row.provider_last_updated))
            row.value = val
            row.updated_at = ts
            revised += 1
        row.retrieved_at = ts
        row.provider_last_updated = o.provider_last_updated or row.provider_last_updated
        row.raw_metadata = o.raw
    return {"created": created, "unchanged": unchanged, "revised": revised}


def obs_out(o: m.ExternalObservation) -> dict:
    revs = len(o.__dict__.get("_revs", []))
    return {
        "id": o.id, "provider": o.provider, "dataset": o.dataset, "indicatorCode": o.indicator_code, "indicatorName": o.indicator_name,
        "countryCode": o.country_code, "countryName": o.country_name, "year": o.year, "value": o.value, "unit": o.unit,
        "sourceOrganization": o.source_organization, "sourceNote": o.source_note, "license": o.license, "sourceUrl": o.source_url,
        "providerLastUpdated": o.provider_last_updated, "retrievedAt": o.retrieved_at, "rawMetadata": o.raw_metadata, "revisions": revs,
    }


def find_obs(db: Session, indicator: str, country: str, year: int, provider: str = "world-bank") -> m.ExternalObservation | None:
    row = db.get(m.ExternalObservation, obs_id(provider, indicator, country, year))
    if row is None and len(country) == 2:  # ISO2 given; observations are keyed by ISO3
        for o in db.scalars(select(m.ExternalObservation).where(m.ExternalObservation.provider == provider,
                                                                m.ExternalObservation.indicator_code == indicator, m.ExternalObservation.year == year)):
            if ((o.raw_metadata or {}).get("country") or {}).get("id", "").upper() == country.upper():
                return o
    return row


# ---------- sources + facts ----------
def ensure_source(db: Session, o: m.ExternalObservation) -> str:
    sid = SOURCE_IDS.get(o.provider) or "SRC-" + hashlib.sha1(f"{o.provider}|{o.dataset}|{o.source_organization}".encode()).hexdigest()[:10]
    if db.get(m.Source, sid) is None:
        ts = now_iso()
        wb = o.provider == "world-bank"
        db.add(m.Source(
            id=sid, created_at=ts, updated_at=ts,
            title=f"{o.dataset} ({'World Bank' if wb else o.source_organization})",
            organization="World Bank" if wb else o.source_organization,
            url="https://data.worldbank.org/" if wb else o.source_url,
            publication_date="", accessed_date=o.retrieved_at[:10], geo_coverage="Global" if wb else o.country_name,
            time_coverage="1960–present" if wb else str(o.year), type="World Bank" if wb else "other",
            reliability="Primary" if wb else "Moderate",
            notes=("Retrieved via the World Bank Indicators API v2. Underlying series compiled by the World Bank from "
                   "national statistical agencies and the IMF; see each observation's source note.") if wb else "Manually entered from the named source."))
        db.flush()
    return sid


def fact_for_observation(db: Session, episode_id: str, o: m.ExternalObservation) -> m.Fact:
    """Create (or reuse) a verified FACT in the episode's ledger that points at the raw observation."""
    fid = "F-OBS-" + hashlib.sha1(f"{episode_id}|{o.id}".encode()).hexdigest()[:12]
    row = db.get(m.Fact, fid)
    sid = ensure_source(db, o)
    ts = now_iso()
    kind = "FX" if o.indicator_code == FX else "CPI" if o.indicator_code == CPI else o.indicator_code
    note = (f"National {o.indicator_name} as published. High confidence applies to the national statistic itself — "
            f"not to the price changes experienced by any specific household, region or income group. "
            f"Retrieved {o.retrieved_at}." + (" Annual period average, not a daily rate." if o.indicator_code == FX else ""))
    fields = dict(
        episode_id=episode_id, category="Economy", metric=f"{o.country_name} {o.indicator_name}", value=o.value, unit=o.unit,
        country=o.country_name, region="National", year_start=o.year, year_end=o.year, source_id=sid, confidence="high",
        fact_type="FACT", derived_from=None, notes=note, status="verified", currency=None, external_observation_id=o.id,
        provider=o.provider, dataset=o.dataset, indicator_code=o.indicator_code, is_prototype=False,
    )
    if row is None:
        row = m.Fact(id=fid, created_at=ts, updated_at=ts, **fields)
        db.add(row)
    elif row.value != o.value or row.external_observation_id != o.id:
        # Never silently rewrite a fact that a calculation already used.
        used = db.scalar(select(m.CalculationInput).where(m.CalculationInput.fact_id == fid))
        if used is None:
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = ts
    db.flush()
    _ = kind
    return row


# ---------- calculations ----------
def _save_derived(db: Session, episode_id: str, r: eng.EngineResult, input_facts: list[tuple[m.Fact, str]], *, metric: str, unit: str,
                  currency: str, country: str, year: int, category: str = "Economy") -> dict:
    ts = now_iso()
    calc_id = "CALC-" + uuid.uuid4().hex[:12]
    fid = "F-DER-" + uuid.uuid4().hex[:10]
    db.add(m.Fact(
        id=fid, created_at=ts, updated_at=ts, episode_id=episode_id, category=category, metric=metric, value=r.result, unit=unit,
        country=country, region="National", year_start=year, year_end=year, source_id=None, confidence="high", fact_type="DERIVED",
        derived_from=f"{r.formula_version}: {r.formula} ({calc_id})", status="verified", currency=currency,
        notes="; ".join(r.labels) + f". Full precision stored; display rounded to 2 dp. Engine {r.engine_version}.",
        provider=None, dataset=None, indicator_code=None, external_observation_id=None, is_prototype=False))
    db.flush()
    db.add(m.DerivedCalculation(id=calc_id, episode_id=episode_id, output_fact_id=fid, calculation_type=r.calculation_type, formula=r.formula,
                                formula_version=r.formula_version, engine_version=r.engine_version, parameters_json=r.parameters,
                                result_json=r.as_dict(), created_at=ts))
    db.flush()
    for f, role in input_facts:
        db.add(m.CalculationInput(calculation_id=calc_id, fact_id=f.id, role=role))
    db.commit()
    return {"calculationId": calc_id, "factId": fid}


def inflation_adjust(db: Session, *, episode_id: str | None, country: str, amount, source_year: int, target_year: int,
                     currency: str | None, save: bool) -> dict:
    country = ISO2_TO_3.get(country.upper(), country.upper())
    currency = currency or CURRENCY_BY_COUNTRY.get(country) or "LCU"
    so, to = find_obs(db, CPI, country, source_year), find_obs(db, CPI, country, target_year)
    r = eng.adjust_for_inflation(amount, source_year, target_year, so.value if so else None, to.value if to else None, country=country, currency=currency)
    out = r.as_dict()
    out["observations"] = [obs_out(o) for o in (so, to) if o]
    if r.status != "OK" or not save:
        return out
    if not episode_id or db.get(m.Episode, episode_id) is None:
        out.update(status="INVALID_INPUT", errors=["Saving requires an existing episode"])
        return out
    fs, ft = fact_for_observation(db, episode_id, so), fact_for_observation(db, episode_id, to)
    out.update(_save_derived(db, episode_id, r, [(fs, "source_cpi"), (ft, "target_cpi")],
                             metric=f"{currency} {amount} of {source_year} in {target_year} {currency} (inflation-adjusted)",
                             unit=f"{currency} ({target_year} prices)", currency=currency, country=so.country_name, year=target_year))
    return out


def currency_convert(db: Session, *, episode_id: str | None, amount, year: int, from_country: str, to_country: str,
                     from_currency: str | None, to_currency: str | None, save: bool) -> dict:
    fc, tc = (ISO2_TO_3.get(c.upper(), c.upper()) for c in (from_country, to_country))
    fcur = from_currency or CURRENCY_BY_COUNTRY.get(fc) or "LCU"
    tcur = to_currency or CURRENCY_BY_COUNTRY.get(tc) or "LCU"
    so = None if fcur == "USD" else find_obs(db, FX, fc, year)
    to = None if tcur == "USD" else find_obs(db, FX, tc, year)
    r = eng.convert_historical_currency(amount, year, fcur, tcur, so.value if so else None, to.value if to else None)
    r.parameters.update(fromCountry=fc, toCountry=tc, precision="annual-average")
    out = r.as_dict()
    out["observations"] = [obs_out(o) for o in (so, to) if o]
    if r.status != "OK" or not save:
        return out
    if not episode_id or db.get(m.Episode, episode_id) is None:
        out.update(status="INVALID_INPUT", errors=["Saving requires an existing episode"])
        return out
    inputs = []
    if so:
        inputs.append((fact_for_observation(db, episode_id, so), "source_fx"))
    if to:
        inputs.append((fact_for_observation(db, episode_id, to), "target_fx"))
    country = (to or so).country_name if (to or so) else tc
    out.update(_save_derived(db, episode_id, r, inputs, metric=f"{fcur} {amount} converted to {tcur} at {year} annual-average rates",
                             unit=f"{tcur} ({year}, annual-average FX)", currency=tcur, country=country, year=year))
    return out


# ---------- lineage ----------
def _fact_node(db: Session, f: m.Fact, depth: int) -> dict:
    src = db.get(m.Source, f.source_id) if f.source_id else None
    o = db.get(m.ExternalObservation, f.external_observation_id) if f.external_observation_id else None
    node = {
        "fact": {"id": f.id, "metric": f.metric, "value": f.value, "unit": f.unit, "factType": f.fact_type, "status": f.status, "year": f.year_start,
                 "country": f.country, "isPrototype": f.is_prototype, "provider": f.provider, "indicatorCode": f.indicator_code},
        "source": {"id": src.id, "title": src.title, "organization": src.organization, "url": src.url, "reliability": src.reliability} if src else None,
        "observation": obs_out(o) if o else None,
        "calculation": None,
    }
    calc = db.scalar(select(m.DerivedCalculation).where(m.DerivedCalculation.output_fact_id == f.id))
    if calc and depth < 5:
        ins = list(db.scalars(select(m.CalculationInput).where(m.CalculationInput.calculation_id == calc.id)))
        values = {"nominal_amount": calc.parameters_json.get("amount")}
        inputs = []
        for ci in ins:
            inf = db.get(m.Fact, ci.fact_id)
            if inf is not None:
                values[ci.role] = inf.value
                inputs.append({"role": ci.role, **_fact_node(db, inf, depth + 1)})
        try:
            rerun = eng.recompute(calc.calculation_type, calc.parameters_json, values)
            reproducible = rerun.status == "OK" and Decimal(rerun.result) == Decimal(f.value)
            rerun_result = rerun.result
        except (ValueError, KeyError, ArithmeticError):
            reproducible, rerun_result = False, None
        node["calculation"] = {
            "id": calc.id, "type": calc.calculation_type, "formula": calc.formula, "formulaVersion": calc.formula_version,
            "engineVersion": calc.engine_version, "parameters": calc.parameters_json, "labels": calc.result_json.get("labels", []),
            "createdAt": calc.created_at, "storedResult": calc.result_json.get("result"), "recomputedResult": rerun_result,
            "reproducible": reproducible, "inputs": inputs,
        }
    return node


def lineage(db: Session, fact_id: str) -> dict | None:
    f = db.get(m.Fact, fact_id)
    return _fact_node(db, f, 0) if f else None


# ---------- verified economic view ----------
def verified_economics(db: Session, episode_id: str, base_year: int) -> dict:
    """Recalculate verified fields for the Economic Ledger on request. Nominal amounts stay PROTOTYPE;
    only the CPI and FX inputs are real. Nothing here overwrites the prototype ledger."""
    rows = sorted(db.scalars(select(m.EconomicYear).where(m.EconomicYear.episode_id == episode_id)), key=lambda y: y.year)
    out = []
    for y in rows:
        country = COUNTRY_BY_CURRENCY.get(y.currency)
        nominal = Decimal(repr(y.income)) + Decimal(repr(y.spouse_income))
        item = {"year": y.year, "currency": y.currency, "country": country, "nominalHousehold": str(nominal), "nominalIsPrototype": True,
                "real": None, "usd": None, "missing": []}
        if country is None:
            item["missing"].append(f"No country mapping for {y.currency}")
        else:
            r = eng.calculate_real_income(nominal, y.year, base_year, *(o.value if o else None for o in (find_obs(db, CPI, country, y.year), find_obs(db, CPI, country, base_year))),
                                          country=country, currency=y.currency)
            item["real"] = r.result if r.status == "OK" else None
            item["missing"] += r.missing
            fxo = find_obs(db, FX, country, y.year) if y.currency != "USD" else None
            c = eng.convert_historical_currency(nominal, y.year, y.currency, "USD", fxo.value if fxo else None, None)
            item["usd"] = c.result if c.status == "OK" else None
            item["missing"] += c.missing
        out.append(item)
    return {"baseYear": base_year, "engineVersion": eng.ENGINE_VERSION, "formulas": [eng.INFLATION_FORMULA, eng.FX_FORMULA],
            "note": "Nominal figures are PROTOTYPE. Real and USD columns use stored World Bank CPI / annual-average FX; computed on request, not saved.",
            "years": out}


# ---------- dataset snapshots ----------
def pin_snapshot(db: Session, episode_id: str, label: str) -> dict:
    facts = db.scalars(select(m.Fact).where(m.Fact.episode_id == episode_id, m.Fact.external_observation_id.is_not(None)))
    items = []
    for f in facts:
        o = db.get(m.ExternalObservation, f.external_observation_id)
        if o:
            items.append({"observationId": o.id, "factId": f.id, "value": o.value, "retrievedAt": o.retrieved_at, "providerLastUpdated": o.provider_last_updated})
    snap = m.EpisodeDatasetSnapshot(id="SNAP-" + uuid.uuid4().hex[:10], episode_id=episode_id, label=label, created_at=now_iso(), items=items)
    db.add(snap)
    db.commit()
    return {"id": snap.id, "episodeId": episode_id, "label": label, "createdAt": snap.created_at, "items": items}


__all__ = ["ProviderError"]
