"""Labour evidence layer: provider observations → normalised wage evidence → deterministic matching
→ human-reviewed baselines → evidence gaps / readiness. No AI, no invented values.

A SOURCE STATISTIC (WageObservation / FACT) is never turned into a character salary. Character income
only exists as an EconomicBaseline (FACT_SUPPORTED / DERIVED / ASSUMPTION) with explicit reasoning."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m
from app.providers.base import Observation
from app.services import truth
from app.services.repository import now_iso

PAY_PERIODS = {"HOURLY", "DAILY", "WEEKLY", "MONTHLY", "ANNUAL"}
STAT_TYPES = {"MEAN", "MEDIAN", "DISTRIBUTION", "OTHER"}
GROSS_NET = {"GROSS", "NET", "UNKNOWN"}
STAGES = [("birth-family", "Birth / family economy"), ("education", "Education"), ("first-employment", "First employment"),
          ("migration-wage", "Migration wage"), ("housing", "Housing"), ("retirement", "Retirement")]
STAGE_LABEL = dict(STAGES)


# ---------------------------------------------------------------- ILO dimension mapping
def _split(code: str, dim: str) -> tuple[str | None, str | None]:
    """'OCU_ISCO08_2' -> ('ISCO-08', '2'); 'EDU_AGGREGATE_ADV' -> ('ILO aggregate', 'ADV')."""
    parts = code.split("_")
    if len(parts) < 3:
        return None, code
    cls, val = parts[1], "_".join(parts[2:])
    pretty = {"ISCO08": "ISCO-08", "ISCO88": "ISCO-88", "ISIC4": "ISIC Rev.4", "ISIC3": "ISIC Rev.3", "ISCED97": "ISCED-97", "ISCED11": "ISCED-11",
              "AGGREGATE": "ILO aggregate", "SKILL": "ILO skill level", "DETAILS": "ILO detailed"}.get(cls, cls)
    return pretty, val


def wage_fields_from_ilo(dims: dict) -> dict:
    f: dict = {}
    sex = (dims.get("SEX") or {}).get("code")
    if sex:
        f["sex"] = {"SEX_T": "TOTAL", "SEX_M": "MALE", "SEX_F": "FEMALE", "SEX_O": "OTHER"}.get(sex, sex)
    if "OCU" in dims:
        cls, val = _split(dims["OCU"]["code"], "OCU")
        f.update(occupation_classification=cls, occupation_code=val, occupation_label=dims["OCU"]["label"])
    if "EDU" in dims:
        cls, val = _split(dims["EDU"]["code"], "EDU")
        f.update(education_classification=cls, education_code=val, education_label=dims["EDU"]["label"])
    if "ECO" in dims:
        cls, val = _split(dims["ECO"]["code"], "ECO")
        f.update(industry_classification=cls, industry_code=val, industry_label=dims["ECO"]["label"])
    if "GEO" in dims:
        f["rural_urban"] = {"GEO_COV_URB": "URBAN", "GEO_COV_RUR": "RURAL", "GEO_COV_NAT": "NATIONAL"}.get(dims["GEO"]["code"], dims["GEO"]["code"])
    if "AGE" in dims:
        f["age_group"] = dims["AGE"]["label"] or dims["AGE"]["code"]
    return f


def _population(f: dict, country: str, year: int, scope: str) -> str:
    bits = [scope, f"{country} {year}"]
    for k, lab in (("sex", "sex"), ("occupation_label", "occupation"), ("education_label", "education"), ("industry_label", "industry"),
                   ("rural_urban", "area"), ("age_group", "age"), ("citizenship", "citizenship"), ("region", "region")):
        if f.get(k) and f.get(k) not in ("TOTAL",):
            bits.append(f"{lab}: {f[k]}")
    return "; ".join(bits)


def upsert_wage_from_ilo(db: Session, o: m.ExternalObservation) -> m.WageObservation | None:
    raw = o.raw_metadata or {}
    if raw.get("concept") != "earnings":
        return None
    ts = now_iso()
    f = wage_fields_from_ilo(raw.get("dims") or {})
    vt = re.search(r"Value type: ([A-Za-z ]+?)(?:\s*\||$)", o.source_note or "")
    fields = dict(
        external_observation_id=o.id, provider=o.provider, country=o.country_code, region=None, year=o.year, period=str(raw.get("period") or o.year),
        frequency=raw.get("freq") or "A", statistic_type=raw.get("statistic") or "OTHER", pay_period=raw.get("payPeriod") or "MONTHLY", value=o.value,
        currency=raw.get("currency"), nominal_or_real=f"AS REPORTED: {vt.group(1).strip()}" if vt else "UNKNOWN",
        gross_or_net="UNKNOWN",  # the ILO feed does not state gross/net per observation; never assumed
        employee_scope="Employees", employment_status="EMPLOYEE", survey_name=(raw.get("attrs") or {}).get("SOURCE") or None,
        source_population=_population(f, o.country_name, o.year, "Employees"), confidence="high",
        notes=o.source_note[:2000], **{k: None for k in ("citizenship", "migrant_status", "formal_informal", "full_part_time")}, **f,
    )
    fields.setdefault("sex", None)
    row = db.get(m.WageObservation, o.id)
    if row is None:
        row = m.WageObservation(id=o.id, created_at=ts, updated_at=ts, **fields)
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = ts
    return row


def wage_out(w: m.WageObservation) -> dict:
    cols = [c.name for c in m.WageObservation.__table__.columns]
    out = {}
    for c in cols:
        parts = c.split("_")
        out[parts[0] + "".join(p.title() for p in parts[1:])] = getattr(w, c)
    return out


def dist_out(db: Session, d: m.WageDistribution) -> dict:
    bins = list(db.scalars(select(m.WageDistributionBin).where(m.WageDistributionBin.distribution_id == d.id).order_by(m.WageDistributionBin.id)))
    return {"id": d.id, "provider": d.provider, "dataset": d.dataset, "country": d.country, "year": d.year, "metric": d.metric, "payPeriod": d.pay_period,
            "currency": d.currency, "dimensions": d.dimensions, "sourceOrganization": d.source_organization, "sourceUrl": d.source_url,
            "bins": [{"lowerBound": b.lower_bound, "upperBound": b.upper_bound, "openLower": b.open_lower, "openUpper": b.open_upper, "count": b.count,
                      "share": b.share, "unit": b.unit, "currency": b.currency, "observationId": b.external_observation_id} for b in bins]}


# ---------------------------------------------------------------- CSV import (manual / MoSPI / UAE)
REQUIRED = ("metric", "unit", "country", "year", "source", "source_organization")
OPTIONAL_DIMS = ("region", "occupation", "occupation_code", "occupation_classification", "education", "industry", "sex", "age_group", "citizenship",
                 "migrant_status", "urban_rural", "employment_status", "formal_informal", "survey")
TEMPLATE_HEADER = ["metric", "value", "unit", "currency", "country", "year", "source", "source_organization", "source_url", "statistic_type", "pay_period",
                   "gross_or_net", *OPTIONAL_DIMS, "bin_lower", "bin_upper", "count", "share", "notes"]


def _num(v: str) -> Decimal | None:
    v = (v or "").replace(",", "").strip()
    if not v:
        return None
    try:
        return Decimal(v)
    except InvalidOperation:
        raise ValueError(f"not a number: {v!r}") from None


def _row_key(provider: str, r: dict) -> str:
    dims = "|".join(f"{k}={(r.get(k) or '').strip().lower()}" for k in OPTIONAL_DIMS)
    basis = "|".join((r.get(k) or "").strip().lower() for k in ("metric", "country", "year", "statistic_type", "pay_period", "bin_lower", "bin_upper", "source"))
    return f"{provider}:" + hashlib.sha1(f"{basis}|{dims}".encode()).hexdigest()[:20]


def parse_import(db: Session, provider: str, text: str) -> dict:
    reader = csv.DictReader(io.StringIO(text.strip()))
    header = [h.strip() for h in (reader.fieldnames or [])]
    missing_cols = [c for c in REQUIRED if c not in header]
    rows: list[dict] = []
    seen: set[str] = set()
    if missing_cols:
        return {"rowsDetected": 0, "valid": 0, "invalid": 0, "duplicates": 0, "changed": 0, "rows": [], "errors": [f"Missing required column(s): {', '.join(missing_cols)}"],
                "template": TEMPLATE_HEADER}
    for i, raw in enumerate(reader, start=2):
        r = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
        errs: list[str] = []
        for c in REQUIRED:
            if not r.get(c):
                errs.append(f"'{c}' is required")
        is_bin = bool(r.get("bin_lower") or r.get("bin_upper"))
        try:
            val = _num(r.get("value", ""))
            cnt, share = _num(r.get("count", "")), _num(r.get("share", ""))
            lo, hi = _num(r.get("bin_lower", "")), _num(r.get("bin_upper", ""))
        except ValueError as e:
            errs.append(str(e))
            val = cnt = share = lo = hi = None
        if is_bin:
            if cnt is None and share is None:
                errs.append("a wage-group row needs 'count' or 'share'")
            if lo is not None and hi is not None and hi < lo:
                errs.append("bin_upper must be >= bin_lower")
        elif val is None:
            errs.append("'value' is required (numeric)")
        if not re.fullmatch(r"[A-Za-z]{3}", r.get("country", "")):
            errs.append("country must be an ISO3 code (e.g. IND, ARE)")
        if not (r.get("year", "").isdigit() and 1800 <= int(r["year"]) <= 2100):
            errs.append("year must be between 1800 and 2100")
        cur = r.get("currency", "").upper()
        if cur and not re.fullmatch(r"[A-Z]{3}", cur):
            errs.append("currency must be an ISO 4217 code")
        if r.get("currency") == "" and not is_bin and "%" not in r.get("unit", "") and val is not None and r.get("pay_period"):
            errs.append("currency is required for a wage value")
        pp = (r.get("pay_period") or "").upper()
        if pp and pp not in PAY_PERIODS:
            errs.append(f"pay_period must be one of {', '.join(sorted(PAY_PERIODS))}")
        st = (r.get("statistic_type") or ("DISTRIBUTION" if is_bin else "OTHER")).upper()
        if st not in STAT_TYPES:
            errs.append(f"statistic_type must be one of {', '.join(sorted(STAT_TYPES))}")
        gn = (r.get("gross_or_net") or "UNKNOWN").upper()
        if gn not in GROSS_NET:
            errs.append("gross_or_net must be GROSS, NET or UNKNOWN")
        key = _row_key(provider, r)
        status = "invalid" if errs else "valid"
        if not errs:
            existing = db.get(m.ExternalObservation, key)
            v_new = str(val if not is_bin else (cnt if cnt is not None else share))
            if key in seen:
                status = "duplicate"
                errs.append("duplicate of an earlier row in this file")
            elif existing is not None:
                status = "duplicate" if Decimal(existing.value) == Decimal(v_new) else "changed"
                if status == "duplicate":
                    errs.append("already imported with the same value")
            seen.add(key)
        rows.append({"line": i, "status": status, "errors": errs, "key": key, "data": r, "statisticType": st, "payPeriod": pp or None, "grossOrNet": gn,
                     "currency": cur or None, "isBin": is_bin})
    count = lambda s: sum(1 for x in rows if x["status"] == s)  # noqa: E731
    return {"rowsDetected": len(rows), "valid": count("valid"), "invalid": count("invalid"), "duplicates": count("duplicate"), "changed": count("changed"),
            "rows": rows, "errors": [], "template": TEMPLATE_HEADER}


def commit_import(db: Session, provider: str, provider_name: str, text: str) -> dict:
    prev = parse_import(db, provider, text)
    if prev["errors"]:
        return {**prev, "imported": 0}
    good = [r for r in prev["rows"] if r["status"] in ("valid", "changed")]
    obs: list[Observation] = []
    for r in good:
        d = r["data"]
        val = _num(d.get("value", "")) if not r["isBin"] else (_num(d.get("count", "")) if d.get("count") else _num(d.get("share", "")))
        dims = {k: d[k] for k in OPTIONAL_DIMS if d.get(k)}
        obs.append(Observation(
            provider=provider, dataset=d["source"], indicator_code="WAGE:" + re.sub(r"[^A-Za-z0-9]+", "-", d["metric"]).strip("-")[:60],
            indicator_name=d["metric"], country_code=d["country"].upper(), country_name=d["country"].upper(), year=int(d["year"]), value=val,
            unit=d["unit"] if not r["isBin"] else ("persons" if d.get("count") else "share"), source_organization=d["source_organization"],
            source_note=d.get("notes", ""), source_url=d.get("source_url", ""),
            raw={"importedFrom": provider_name, "row": d, "dims": dims, "statistic": r["statisticType"], "payPeriod": r["payPeriod"], "currency": r["currency"],
                 "grossOrNet": r["grossOrNet"], "region": d.get("region") or None, "concept": "earnings" if r["payPeriod"] or r["isBin"] else "other"},
            obs_key=r["key"]))
    counts = truth.store_observations(db, obs)
    db.flush()
    ts = now_iso()
    for r in good:
        d = r["data"]
        o = db.get(m.ExternalObservation, r["key"])
        if r["isBin"]:
            dkey = f"{provider}:dist:" + hashlib.sha1("|".join([d["metric"], d["country"].upper(), d["year"], d["source"], *(d.get(k, "") for k in OPTIONAL_DIMS)]).encode()).hexdigest()[:16]
            if db.get(m.WageDistribution, dkey) is None:
                db.add(m.WageDistribution(id=dkey, provider=provider, dataset=d["source"], country=d["country"].upper(), year=int(d["year"]), metric=d["metric"],
                                          pay_period=r["payPeriod"] or "MONTHLY", currency=r["currency"], dimensions={k: d[k] for k in OPTIONAL_DIMS if d.get(k)},
                                          source_organization=d["source_organization"], source_url=d.get("source_url", ""), created_at=ts))
                db.flush()
            existing_bin = db.scalar(select(m.WageDistributionBin).where(m.WageDistributionBin.external_observation_id == r["key"]))
            lo, hi = d.get("bin_lower") or None, d.get("bin_upper") or None
            fields = dict(distribution_id=dkey, lower_bound=lo.replace(",", "") if lo else None, upper_bound=hi.replace(",", "") if hi else None,
                          open_lower=lo is None, open_upper=hi is None, count=d.get("count") or None, share=d.get("share") or None,
                          unit=d["unit"], currency=r["currency"], external_observation_id=r["key"])
            if existing_bin is None:
                db.add(m.WageDistributionBin(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing_bin, k, v)
            continue
        if not r["payPeriod"]:
            continue  # non-wage statistic: stays an external observation only
        f = {"region": d.get("region") or None, "occupation_label": d.get("occupation") or None, "occupation_code": d.get("occupation_code") or None,
             "occupation_classification": d.get("occupation_classification") or None, "education_label": d.get("education") or None,
             "industry_label": d.get("industry") or None, "sex": (d.get("sex") or "").upper() or None, "age_group": d.get("age_group") or None,
             "citizenship": (d.get("citizenship") or "").upper() or None, "migrant_status": d.get("migrant_status") or None,
             "rural_urban": (d.get("urban_rural") or "").upper() or None, "employment_status": (d.get("employment_status") or "").upper() or None,
             "formal_informal": (d.get("formal_informal") or "").upper() or None}
        fields = dict(external_observation_id=o.id, provider=provider, country=o.country_code, year=o.year, period=str(o.year), frequency="A",
                      statistic_type=r["statisticType"], pay_period=r["payPeriod"], value=o.value, currency=r["currency"], nominal_or_real="UNKNOWN",
                      gross_or_net=r["grossOrNet"], employee_scope=d.get("employment_status") or None, survey_name=d.get("survey") or None,
                      source_population=_population({**f}, o.country_code, o.year, d.get("employment_status") or "Population as published"),
                      confidence="medium" if provider == "manual" else "high", notes=d.get("notes", ""), full_part_time=None, education_code=None,
                      education_classification=None, industry_code=None, industry_classification=None, **f)
        w = db.get(m.WageObservation, o.id)
        if w is None:
            db.add(m.WageObservation(id=o.id, created_at=ts, updated_at=ts, **fields))
        else:
            for k, v in fields.items():
                setattr(w, k, v)
            w.updated_at = ts
    db.commit()
    return {**{k: prev[k] for k in ("rowsDetected", "valid", "invalid", "duplicates", "changed")}, "imported": len(good), **counts}


# ---------------------------------------------------------------- profiles
PROFILE_KEYS = ("country", "region", "urbanRural", "educationLevel", "occupation", "occupationCode", "occupationClassification", "industry", "industryCode",
                "employmentStatus", "formalInformal", "yearsExperience", "age", "sex", "citizenship", "migrantStatus", "employmentSector", "notes")


def profile_out(p: m.CharacterEconomicProfile) -> dict:
    return {"id": p.id, "episodeId": p.episode_id, "lifeStage": p.life_stage, "lifeStageLabel": STAGE_LABEL.get(p.life_stage, p.life_stage),
            "targetYear": p.target_year, "yearStart": p.year_start, "yearEnd": p.year_end, **{k: p.fields.get(k) for k in PROFILE_KEYS},
            "createdAt": p.created_at, "updatedAt": p.updated_at}


# ---------------------------------------------------------------- deterministic evidence matcher
def _norm(x) -> str:
    return str(x or "").strip().upper()


def score_candidate(p: dict, target_year: int, w: m.WageObservation) -> dict:
    """Evidence Match Score (0–100). An explainable ranking of how closely a published statistic's
    population matches the profile — NOT a probability that a salary is correct."""
    parts: list[dict] = []

    def add(dim: str, pts: int, mx: int, note: str):
        parts.append({"dimension": dim, "points": pts, "max": mx, "note": note})

    cc = _norm(p.get("country"))
    add("Country", 25 if w.country == cc else 0, 25, "Exact country" if w.country == cc else f"Different country ({w.country} vs {cc or '—'})")
    d = abs(w.year - target_year)
    add("Year", max(0, 20 - 3 * d), 20, "Exact year" if d == 0 else f"Source {w.year} vs target {target_year} ({d} yr{'s' if d != 1 else ''})")
    occ, ocls = _norm(p.get("occupationCode")), p.get("occupationClassification") or "ISCO-08"
    if not occ:
        add("Occupation", 0, 15, "Profile occupation code not specified")
    elif w.occupation_code is None:
        add("Occupation", 3, 15, "Source has no occupation breakdown (all employees)")
    elif _norm(w.occupation_code) == "TOTAL":
        add("Occupation", 5, 15, f"All occupations ({w.occupation_classification})")
    elif _norm(w.occupation_code) == occ and w.occupation_classification == ocls:
        add("Occupation", 15, 15, f"Exact occupation: {w.occupation_label} ({w.occupation_classification})")
    elif _norm(w.occupation_code) == occ and (w.occupation_classification or "").startswith("ISCO"):
        add("Occupation", 7, 15, f"Same major group in {w.occupation_classification} vs profile {ocls} — classification versions not assumed equivalent")
    else:
        add("Occupation", 0, 15, f"Different occupation: {w.occupation_label or w.occupation_code}")
    edu = _norm(p.get("educationLevel"))
    wc = _norm(w.education_code)
    if not edu:
        add("Education", 0, 10, "Profile education not specified")
    elif w.education_code is None:
        add("Education", 2, 10, "Source has no education breakdown")
    elif wc == "TOTAL":
        add("Education", 3, 10, "All education levels")
    elif wc == edu and w.education_classification == "ILO aggregate":
        add("Education", 10, 10, f"Education matched: {w.education_label}")
    else:
        add("Education", 0, 10, f"Different education level: {w.education_label or w.education_code}")
    es, ws = _norm(p.get("employmentStatus")), _norm(w.employment_status)
    if not es or es == "UNKNOWN":
        add("Employment status", 0, 10, "Profile employment status not specified")
    elif ws and es == ws:
        add("Employment status", 10, 10, f"Both {es.lower()}")
    elif es == "SELF_EMPLOYED" and ws == "EMPLOYEE":
        add("Employment status", 0, 10, "Employee earnings vs self-employed character — needs an explicit assumption")
    else:
        add("Employment status", 0, 10, f"Source employment status {ws.lower() or 'unavailable'}")
    ur, wu = _norm(p.get("urbanRural")), _norm(w.rural_urban)
    if not ur:
        add("Urban/rural", 0, 5, "Profile urban/rural not specified")
    elif not wu:
        add("Urban/rural", 0, 5, "Urban/rural unavailable in source")
    elif wu == ur:
        add("Urban/rural", 5, 5, f"{ur.title()} matched")
    elif wu == "NATIONAL":
        add("Urban/rural", 2, 5, "National figure, not area-specific")
    else:
        add("Urban/rural", 0, 5, f"Source is {wu.lower()}")
    sx, wsx = _norm(p.get("sex")), _norm(w.sex)
    if not sx or not wsx:
        add("Sex", 0, 5, "Sex unavailable" if not wsx else "Profile sex not specified")
    elif wsx == sx:
        add("Sex", 5, 5, f"{sx.title()} matched")
    elif wsx == "TOTAL":
        add("Sex", 2, 5, "Both sexes combined")
    else:
        add("Sex", 0, 5, f"Source is {wsx.lower()}")
    rg = (p.get("region") or "").strip().lower()
    if not rg:
        add("Region", 0, 5, "Profile region not specified")
    elif not w.region:
        add("Region", 0, 5, "Region unavailable (national statistic)")
    elif w.region.lower() in rg or rg in w.region.lower():
        add("Region", 5, 5, f"Region matched: {w.region}")
    else:
        add("Region", 0, 5, f"Different region: {w.region}")
    cz, wcz = _norm(p.get("citizenship")), _norm(w.citizenship)
    if not cz:
        add("Citizenship / migrant", 0, 5, "Profile citizenship not specified")
    elif not wcz:
        add("Citizenship / migrant", 0, 5, "Citizenship/migrant status unavailable in source")
    elif wcz == cz:
        add("Citizenship / migrant", 5, 5, f"Citizenship matched: {wcz.lower()}")
    elif wcz == "TOTAL":
        add("Citizenship / migrant", 1, 5, "Nationals and non-nationals combined")
    else:
        add("Citizenship / migrant", 0, 5, f"Source citizenship {wcz.lower()}")
    total = sum(x["points"] for x in parts)
    return {"score": total, "breakdown": parts, "yearDistance": d, "sourceYear": w.year, "targetYear": target_year,
            "countryMatch": w.country == cc, "label": "Evidence Match Score (not a probability)"}


def candidates(db: Session, prof: m.CharacterEconomicProfile, limit: int = 25) -> dict:
    p = prof.fields
    reviews = {r.wage_observation_id: r for r in db.scalars(select(m.CandidateReview).where(m.CandidateReview.profile_id == prof.id))}
    out = []
    for w in db.scalars(select(m.WageObservation)):
        s = score_candidate(p, prof.target_year, w)
        rv = reviews.get(w.id)
        out.append({"wage": wage_out(w), **s, "review": {"decision": rv.decision, "note": rv.note} if rv else None})
    out.sort(key=lambda c: (c["review"] is not None and c["review"]["decision"] == "rejected", -c["score"], c["yearDistance"], c["wage"]["id"]))
    cc = _norm(p.get("country"))
    dists = [dist_out(db, d) for d in db.scalars(select(m.WageDistribution).where(m.WageDistribution.country == cc))]
    dists.sort(key=lambda d: abs(d["year"] - prof.target_year))
    return {"profile": profile_out(prof), "candidates": out[:limit], "totalConsidered": len(out),
            "distributions": [{**d, "yearDistance": abs(d["year"] - prof.target_year)} for d in dists[:10]],
            "note": "Ranking is deterministic and explainable. It measures population match, not salary probability."}


# ---------------------------------------------------------------- baselines
def confidence_for(scores: list[dict]) -> tuple[str, list[str]]:
    if not scores:
        return "INSUFFICIENT_DATA", ["No accepted evidence"]
    best = max(s["score"] for s in scores)
    dmin = min(s["yearDistance"] for s in scores)
    reasons = [f"Best Evidence Match Score {best}/100", f"Closest source year is {dmin} year(s) from target", f"{len(scores)} supporting observation(s)"]
    if not all(s["countryMatch"] for s in scores):
        reasons.append("Some evidence is from a different country")
        return "INSUFFICIENT_DATA", reasons
    if best >= 80 and dmin == 0:
        lvl = "HIGH"
    elif best >= 60 and dmin <= 2:
        lvl = "MEDIUM"
    elif best >= 35 and dmin <= 5:
        lvl = "LOW"
    else:
        lvl = "INSUFFICIENT_DATA"
    reasons.append("Confidence is a rule-based label, not a validated probability")
    return lvl, reasons


class BaselineError(ValueError):
    pass


def create_baseline(db: Session, episode_id: str, req: dict) -> m.EconomicBaseline:
    prof = db.get(m.CharacterEconomicProfile, req["profileId"]) if req.get("profileId") else None
    if prof is not None and prof.episode_id != episode_id:
        raise BaselineError("Profile belongs to another episode")
    btype = req["baselineType"]
    target = req.get("adjustToYear") or (prof.target_year if prof else req["yearStart"])
    ws = [db.get(m.WageObservation, i) for i in req.get("wageObservationIds", [])]
    if any(w is None for w in ws):
        raise BaselineError("Unknown wage observation")
    for fid in req.get("evidenceFactIds", []):
        f = db.get(m.Fact, fid)
        if f is None:
            raise BaselineError(f"Unknown fact {fid}")
        if f.is_prototype and btype != "ASSUMPTION":
            raise BaselineError("PROTOTYPE values cannot support a verified baseline")
    if btype in ("FACT_SUPPORTED", "DERIVED") and not ws:
        raise BaselineError("A fact-supported or derived baseline needs accepted wage evidence")
    if len({(w.currency, w.pay_period) for w in ws}) > 1:
        raise BaselineError("Evidence mixes currencies or pay periods; normalise explicitly first")
    p = prof.fields if prof else {"country": ws[0].country if ws else ""}
    scores = [score_candidate(p, target if btype != "DERIVED" else (prof.target_year if prof else target), w) for w in ws]
    ts = now_iso()
    bid = "BL-" + uuid.uuid4().hex[:10]
    evidence, fact_ids, calc_ids = [], [], []
    values: list[Decimal] = []
    for w, s in zip(ws, scores):
        o = db.get(m.ExternalObservation, w.external_observation_id)
        f = truth.fact_for_observation(db, episode_id, o)
        fact_ids.append(f.id)
        evidence.append({"wageObservationId": w.id, "observationId": o.id, "factId": f.id, "score": s["score"], "yearDistance": s["yearDistance"], "sourceYear": w.year,
                         "value": w.value, "statisticType": w.statistic_type, "population": w.source_population, "observationUpdatedAt": o.updated_at})
        values.append(Decimal(w.value))
    currency = ws[0].currency if ws else (req.get("currency") or "")
    pay = ws[0].pay_period if ws else (req.get("payPeriod") or "MONTHLY")
    gross = ws[0].gross_or_net if ws and len({w.gross_or_net for w in ws}) == 1 else "UNKNOWN"
    conf, reasons = confidence_for(scores)
    low = high = point = None
    assumption_fact = None
    if btype == "FACT_SUPPORTED":
        if any(s["yearDistance"] for s in scores):
            raise BaselineError("FACT_SUPPORTED requires evidence from the target year; use DERIVED (CPI-adjusted) or ASSUMPTION")
        if conf == "INSUFFICIENT_DATA":
            raise BaselineError("Evidence is insufficient for a fact-supported baseline")
    elif btype == "DERIVED":
        if not req.get("adjustToYear"):
            raise BaselineError("DERIVED baseline needs adjustToYear (CPI adjustment)")
        derived = []
        for w, ev in zip(ws, evidence):
            r = truth.inflation_adjust(db, episode_id=episode_id, country=w.country, amount=w.value, source_year=w.year, target_year=int(req["adjustToYear"]),
                                       currency=w.currency, save=True)
            if r["status"] != "OK":
                db.rollback()
                raise BaselineError("CPI adjustment not possible: " + "; ".join(r.get("missing") or r.get("errors") or ["missing data"]))
            calc_ids.append(r["calculationId"])
            fact_ids.append(r["factId"])
            ev["derivedFactId"], ev["derivedValue"] = r["factId"], r["result"]
            derived.append(Decimal(r["result"]))
        values = derived
        if any(s["yearDistance"] > 5 for s in scores):
            reasons.append("Evidence is more than 5 years from the target year — CPI adjustment does not make it historical fact")
            conf = "LOW" if conf in ("HIGH", "MEDIUM") else conf
    if btype == "ASSUMPTION":
        reasoning = (req.get("reasoning") or "").strip()
        if len(reasoning) < 20:
            raise BaselineError("An ASSUMPTION baseline needs written reasoning (at least 20 characters)")
        low, high, point = (str(Decimal(str(req[k]).replace(",", ""))) if req.get(k) not in (None, "") else None for k in ("low", "high", "point"))
        if low is None and high is None and point is None:
            raise BaselineError("Give a point value or a range")
        if low and high and Decimal(high) < Decimal(low):
            raise BaselineError("high must be >= low")
        if not currency:
            raise BaselineError("currency is required")
        conf = "LOW" if conf != "INSUFFICIENT_DATA" or ws else "INSUFFICIENT_DATA"
        reasons.append("Character-specific assumption, not a source statistic")
        afid = "F-ASM-" + uuid.uuid4().hex[:10]
        shown = point or f"{low or '…'}–{high or '…'}"
        assumption_fact = m.Fact(id=afid, created_at=ts, updated_at=ts, episode_id=episode_id, category="Employment",
                                 metric=f"ASSUMED {STAGE_LABEL.get(req['lifeStage'], req['lifeStage'])} income ({req.get('occupation') or 'character'})",
                                 value=shown, unit=f"{currency} per {pay.lower()}", country=p.get("country") or "", region=p.get("region") or "",
                                 year_start=int(req["yearStart"]), year_end=int(req["yearEnd"]), source_id=None, confidence="low", fact_type="ASSUMPTION",
                                 derived_from=None, notes=f"{reasoning} Evidence facts: {', '.join(fact_ids) or 'none'}.", status="unverified",
                                 currency=currency, is_prototype=False)
        db.add(assumption_fact)
        db.flush()
    else:
        vs = sorted(values)
        if len(vs) == 1:
            point = str(vs[0])
        else:
            low, high = str(vs[0]), str(vs[-1])
    annual = req.get("annualization")
    if annual:
        from app.services import economic_engine as eng
        r = eng.annualize_wage(point or low or high, pay, annual.get("assumptions", {}))
        if r.status != "OK":
            raise BaselineError("Annualization needs explicit assumptions: " + "; ".join(r.missing + r.errors))
        annual = {"method": eng.ANNUALIZE_FORMULA, "assumptions": annual.get("assumptions", {}), "fromPayPeriod": pay,
                  "low": str(eng.annualize_wage(low, pay, annual["assumptions"]).result) if low else None,
                  "high": str(eng.annualize_wage(high, pay, annual["assumptions"]).result) if high else None,
                  "point": str(eng.annualize_wage(point, pay, annual["assumptions"]).result) if point else None}
    req_gn = (req.get("grossOrNet") or "").upper()
    if req_gn == "NET" and gross != "NET":
        raise BaselineError("Evidence is not reported as net income; LifeSpan does not compute take-home pay (taxes are a later phase)")
    b = m.EconomicBaseline(
        id=bid, episode_id=episode_id, profile_id=prof.id if prof else None, life_stage=req["lifeStage"], year_start=int(req["yearStart"]), year_end=int(req["yearEnd"]),
        employment_type=req.get("employmentType") or (p.get("employmentStatus") or ""), occupation=req.get("occupation") or (p.get("occupation") or ""),
        baseline_type=btype, estimate_kind="POINT" if point else "RANGE", low=low, high=high, point=point, currency=currency, pay_period=pay,
        gross_or_net=gross, annualization=annual, confidence=conf, confidence_reasons=reasons, reasoning=(req.get("reasoning") or "").strip(),
        evidence=evidence, source_fact_ids=fact_ids + list(req.get("evidenceFactIds", [])), derived_calculation_ids=calc_ids,
        assumption_fact_id=assumption_fact.id if assumption_fact else None, user_approved=False, approved_at=None, created_at=ts, updated_at=ts)
    db.add(b)
    db.commit()
    return b


def baseline_out(db: Session, b: m.EconomicBaseline) -> dict:
    proto = [{"year": y.year, "income": y.income, "spouseIncome": y.spouse_income, "currency": y.currency}
             for y in db.scalars(select(m.EconomicYear).where(m.EconomicYear.episode_id == b.episode_id, m.EconomicYear.year >= b.year_start,
                                                              m.EconomicYear.year <= b.year_end).order_by(m.EconomicYear.year))]
    pinned = db.scalar(select(m.SnapshotBaseline.snapshot_id).join(m.EpisodeDatasetSnapshot, m.EpisodeDatasetSnapshot.id == m.SnapshotBaseline.snapshot_id)
                       .where(m.SnapshotBaseline.economic_baseline_id == b.id, m.EpisodeDatasetSnapshot.status == "final"))
    return {"id": b.id, "episodeId": b.episode_id, "profileId": b.profile_id, "lifeStage": b.life_stage, "lifeStageLabel": STAGE_LABEL.get(b.life_stage, b.life_stage),
            "yearStart": b.year_start, "yearEnd": b.year_end, "employmentType": b.employment_type, "occupation": b.occupation, "baselineType": b.baseline_type,
            "estimateKind": b.estimate_kind, "low": b.low, "high": b.high, "point": b.point, "currency": b.currency, "payPeriod": b.pay_period,
            "grossOrNet": b.gross_or_net, "annualization": b.annualization, "confidence": b.confidence, "confidenceReasons": b.confidence_reasons,
            "reasoning": b.reasoning, "evidence": b.evidence, "sourceFactIds": b.source_fact_ids, "derivedCalculationIds": b.derived_calculation_ids,
            "assumptionFactId": b.assumption_fact_id, "userApproved": b.user_approved, "approvedAt": b.approved_at, "createdAt": b.created_at,
            "pinnedInSnapshot": pinned, "prototypeIncome": {"isPrototype": True, "note": "Economic Ledger demo values (annual, PROTOTYPE) — not replaced", "years": proto}}


# ---------------------------------------------------------------- gaps + readiness
GAP_CATEGORY = {"first-employment": "Employment", "migration-wage": "Migration", "education": "Education", "housing": "Housing",
                "birth-family": "Economy", "retirement": "Economy"}


def detect_gaps(db: Session, episode_id: str) -> list[m.EvidenceGap]:
    ts = now_iso()
    found: dict[str, dict] = {}
    profiles = list(db.scalars(select(m.CharacterEconomicProfile).where(m.CharacterEconomicProfile.episode_id == episode_id)))
    approved_stages = {b.life_stage for b in db.scalars(select(m.EconomicBaseline).where(m.EconomicBaseline.episode_id == episode_id, m.EconomicBaseline.user_approved))}
    for pr in profiles:
        c = candidates(db, pr, limit=5)["candidates"]
        good = [x for x in c if x["countryMatch"] and x["score"] >= 50 and x["yearDistance"] <= 3 and not (x["review"] and x["review"]["decision"] == "rejected")]
        if good or pr.life_stage in approved_stages:
            continue
        best = c[0] if c else None
        what = pr.fields.get("occupation") or "employee"
        place = pr.fields.get("region") or pr.fields.get("country") or ""
        reason = ("No wage observations stored for this country" if not best or not best["countryMatch"] else
                  f"Closest evidence: score {best['score']}/100, source year {best['sourceYear']} ({best['yearDistance']} yrs from {pr.target_year})")
        found[f"profile:{pr.id}"] = dict(title=f"{pr.year_start}–{pr.year_end} {place} {what} wages", reason=f"{reason}. Required for the {STAGE_LABEL.get(pr.life_stage, pr.life_stage)} baseline.",
                                         category=GAP_CATEGORY.get(pr.life_stage, "Employment"), country=pr.fields.get("country") or "", year_start=pr.year_start,
                                         year_end=pr.year_end, priority="HIGH" if pr.life_stage in ("first-employment", "migration-wage") else "MEDIUM")
    ep = db.get(m.Episode, episode_id)
    birth = ep.character.birth_year if ep and ep.character else 1900
    facts = list(db.scalars(select(m.Fact).where(m.Fact.episode_id == episode_id, m.Fact.is_prototype.is_(False))))
    for stage, cat, label, yrs in (("housing", "Housing", "housing costs / rents", (birth + 20, birth + 65)),
                                   ("education", "Education", "education costs", (birth + 5, birth + 22)),
                                   ("retirement", "Economy", "pension / retirement income", (birth + 60, birth + 80))):
        if stage in approved_stages or any(f.category == cat and f.status == "verified" for f in facts):
            continue
        found[f"stage:{stage}"] = dict(title=f"{yrs[0]}–{yrs[1]} {label}", reason="No verified evidence stored and no free LifeSpan provider covers this yet.",
                                       category=cat, country=ep.character.country if ep and ep.character else "", year_start=yrs[0], year_end=yrs[1], priority="MEDIUM")
    existing = {g.gap_key: g for g in db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == episode_id))}
    for key, g in existing.items():
        if g.auto and key not in found and g.status == "open":
            g.status = "resolved"
    for key, v in found.items():
        g = existing.get(key)
        if g is None:
            db.add(m.EvidenceGap(id="GAP-" + uuid.uuid4().hex[:8], episode_id=episode_id, gap_key=key, status="open", auto=True, created_at=ts, **v))
        else:
            for k, val in v.items():
                setattr(g, k, val)
            if g.status == "resolved":
                g.status = "open"
    db.commit()
    return list(db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == episode_id).order_by(m.EvidenceGap.priority, m.EvidenceGap.created_at)))


def gap_out(g: m.EvidenceGap) -> dict:
    return {"id": g.id, "episodeId": g.episode_id, "gapKey": g.gap_key, "title": g.title, "reason": g.reason, "category": g.category, "country": g.country,
            "yearStart": g.year_start, "yearEnd": g.year_end, "priority": g.priority, "status": g.status, "auto": g.auto, "researchTaskId": g.research_task_id,
            "createdAt": g.created_at}


TASK_CATEGORY = {"Employment": "Employment", "Migration": "Migration", "Education": "Education", "Housing": "Housing", "Economy": "Economy"}


def task_from_gap(db: Session, g: m.EvidenceGap) -> m.ResearchTask:
    if g.research_task_id and db.get(m.ResearchTask, g.research_task_id):
        return db.get(m.ResearchTask, g.research_task_id)
    ts = now_iso()
    t = m.ResearchTask(id="RT-GAP-" + uuid.uuid4().hex[:8], created_at=ts, updated_at=ts, episode_id=g.episode_id, category=TASK_CATEGORY.get(g.category, "Economy"),
                       question=f"Find authoritative statistics for: {g.title} ({g.country}). {g.reason}", period=f"{g.year_start}–{g.year_end}",
                       status="pending", assigned_to="", fact_ids=[])
    db.add(t)
    g.research_task_id = t.id
    db.commit()
    return t


def readiness(db: Session, episode_id: str) -> dict:
    profiles = list(db.scalars(select(m.CharacterEconomicProfile).where(m.CharacterEconomicProfile.episode_id == episode_id)))
    baselines = list(db.scalars(select(m.EconomicBaseline).where(m.EconomicBaseline.episode_id == episode_id)))
    facts = list(db.scalars(select(m.Fact).where(m.Fact.episode_id == episode_id, m.Fact.is_prototype.is_(False), m.Fact.status == "verified")))
    out = []
    for key, label in STAGES:
        bl = [b for b in baselines if b.life_stage == key]
        why = []
        if any(b.user_approved for b in bl):
            st = "READY"
            why.append("Approved economic baseline exists")
        elif bl:
            st = "PARTIAL"
            why.append("Baseline drafted but not approved")
        else:
            pr = [p for p in profiles if p.life_stage == key]
            best = max((c["score"] for p in pr for c in candidates(db, p, 3)["candidates"] if c["countryMatch"]), default=None)
            cat = {"housing": "Housing", "education": "Education"}.get(key)
            if best is not None and best >= 35:
                st = "PARTIAL"
                why.append(f"Candidate evidence found (best score {best}/100) but no baseline")
            elif cat and any(f.category == cat for f in facts):
                st = "PARTIAL"
                why.append(f"Verified {cat.lower()} facts exist but no baseline")
            else:
                st = "MISSING"
                why.append("No profile evidence" if pr else "No profile or evidence for this stage")
        out.append({"stage": key, "label": label, "status": st, "reasons": why})
    pct = round(100 * sum(1 if s["status"] == "READY" else 0.5 if s["status"] == "PARTIAL" else 0 for s in out) / len(out))
    return {"stages": out, "overall": pct, "note": "Measures whether required evidence exists — not prediction confidence."}
