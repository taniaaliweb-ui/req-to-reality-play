"""Phase 5 Life Context Evidence Engine (deterministic, no AI, no prediction).

Builds the evidence a later simulation will consume: normalised population evidence per life
domain, explainable Evidence Match Scores (NOT probabilities), explicit temporal coverage
(DIRECT / NEARBY / DERIVED / ASSUMED / MISSING), event relevance, the Life Evidence Matrix,
readiness, gaps, life-stage baselines and the assumption register. Population statistics are never
turned into individual outcomes; missing evidence stays MISSING."""
from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db import models as m
from app.providers.base import Observation
from app.services.repository import now_iso

# ------------------------------------------------------------------ vocabulary
DATA_DOMAINS = ["demographic", "mortality", "fertility", "migration", "education", "education_cost", "housing", "household_expenditure",
                "family_formation", "retirement", "pension", "employment_context"]

# Domain-specific validity windows (max |year distance| for NEARBY). Stored + explained, never silent.
VALIDITY_WINDOW = {"income": 1, "demographic": 2, "mortality": 2, "fertility": 2, "migration": 3, "education": 3, "education_cost": 2,
                   "housing": 2, "household_expenditure": 3, "family_formation": 5, "retirement": 5, "pension": 5, "employment_context": 2,
                   "context": 10}
WINDOW_REASON = {"income": "Wages change quickly; only adjacent years count as nearby.",
                 "demographic": "Population structure changes slowly.", "mortality": "Mortality schedules change slowly year to year.",
                 "fertility": "Fertility rates change gradually.", "migration": "Migration statistics are often published every few years.",
                 "education": "Enrollment statistics are irregular; moderate window.", "education_cost": "Costs change with prices; tight window.",
                 "housing": "Housing costs are price-sensitive; tight window.", "household_expenditure": "Household surveys run every few years.",
                 "family_formation": "Marriage-age patterns shift slowly; survey rounds are years apart.",
                 "retirement": "Retirement rules/ages change rarely.", "pension": "Pension rules change rarely.",
                 "employment_context": "Labour-market rates change yearly.", "context": "Qualitative context may describe a longer period."}

# Matrix domains → which normalised data domains count as evidence
MATRIX_DOMAINS = [
    ("demographic", "Demographic", ["demographic"]),
    ("education", "Education", ["education", "education_cost"]),
    ("income", "Income", []),
    ("housing", "Housing", ["housing"]),
    ("household_spending", "Household spending", ["household_expenditure"]),
    ("marriage", "Marriage", ["family_formation"]),
    ("fertility", "Fertility", ["fertility"]),
    ("migration", "Migration", ["migration"]),
    ("mortality", "Health / mortality", ["mortality"]),
    ("retirement", "Retirement", ["retirement", "pension"]),
    ("historical", "Historical context", []),
]
MATRIX_LABEL = {k: v for k, v, _ in MATRIX_DOMAINS}
MATRIX_SOURCES = {k: s for k, _, s in MATRIX_DOMAINS}
WINDOW_FOR = {"demographic": 2, "education": 3, "income": 1, "housing": 2, "household_spending": 3, "marriage": 5, "fertility": 2,
              "migration": 3, "mortality": 2, "retirement": 5, "historical": 0}
GEO_SENSITIVE = {"income", "housing", "household_spending"}  # national evidence ≠ city fact

# Life stages: (key, label, critical matrix domains, other applicable domains)
STAGES = [
    ("birth", "Birth", ["demographic", "mortality"], ["fertility", "historical"]),
    ("childhood", "Childhood", ["mortality", "household_spending"], ["demographic", "housing", "historical"]),
    ("school", "School", ["education"], ["household_spending", "historical"]),
    ("higher-education", "Higher Education", ["education"], ["historical"]),
    ("first-job", "First Job", ["income"], ["housing", "historical"]),
    ("marriage-family", "Marriage / Family", ["marriage", "fertility"], ["housing", "historical"]),
    ("migration", "Migration", ["migration", "income"], ["housing", "historical"]),
    ("mid-career", "Mid-Career", ["income", "housing", "household_spending"], ["historical"]),
    ("children-education", "Children / Education", ["education"], ["fertility", "household_spending"]),
    ("late-career", "Late Career", ["income"], ["housing", "historical"]),
    ("retirement", "Retirement", ["retirement"], ["income", "historical"]),
    ("old-age", "Old Age", ["mortality"], ["demographic", "household_spending"]),
    ("death", "Death", ["mortality"], []),
]
STAGE_LABEL = {k: lbl for k, lbl, _, _ in STAGES}

READINESS_GROUPS = [
    ("demographic", "Demographic readiness", ["demographic", "mortality"]),
    ("education", "Education readiness", ["education"]),
    ("career", "Career readiness", ["income"]),
    ("household", "Household readiness", ["household_spending"]),
    ("family", "Marriage/family readiness", ["marriage", "fertility"]),
    ("housing", "Housing readiness", ["housing"]),
    ("migration", "Migration readiness", ["migration"]),
    ("retirement", "Retirement readiness", ["retirement"]),
    ("historical", "Historical-context readiness", ["historical"]),
]

NEED = {"demographic": "population structure statistics", "education": "enrollment / completion / education-cost statistics",
        "income": "wage observations for the character's occupation", "housing": "rent / housing-cost statistics for the city",
        "household_spending": "household expenditure survey data", "marriage": "age at first marriage / marriage-rate statistics",
        "fertility": "fertility statistics", "migration": "migration flow / migrant-stock statistics", "mortality": "mortality / life-expectancy statistics",
        "retirement": "retirement age, pension eligibility and coverage evidence", "historical": "historical events registry entries"}
TASK_CAT = {"demographic": "Demographics", "mortality": "Demographics", "fertility": "Demographics", "marriage": "Social environment",
            "education": "Education", "income": "Employment", "housing": "Housing", "household_spending": "Economy", "migration": "Migration",
            "retirement": "Economy", "historical": "Historical context"}

# Future hooks only (Phase 6+) — no simulation here.
FUTURE_HOOKS = {
    "outlierCategories": ["poor-to-wealthy", "wealthy-to-poor", "career-breakthrough", "business-success", "business-failure", "migration-success",
                          "migration-failure", "inheritance", "financial-collapse"],
    "narrativeImpact": ["stress", "grief", "pride", "isolation", "regret", "joy"],
    "note": "Evidence categories only. Outcomes will be probabilistic and context-sensitive (Phase 6); emotions belong to narrative interpretation, not truth data.",
}

OFFICIAL_PROVIDERS = {"un-wpp", "world-bank", "ilostat", "india-mospi", "uae-fcsc"}
REGION_GROUPS = {"GCC": {"ARE", "SAU", "KWT", "QAT", "BHR", "OMN"}, "SOUTH_ASIA": {"IND", "PAK", "BGD", "LKA", "NPL", "BTN", "MDV", "AFG"}}
COUNTRY_ISO3 = {"india": "IND", "united arab emirates": "ARE", "uae": "ARE", "dubai": "ARE", "abu dhabi": "ARE", "pakistan": "PAK", "bangladesh": "BGD",
                "nepal": "NPL", "sri lanka": "LKA", "saudi arabia": "SAU", "kuwait": "KWT", "qatar": "QAT", "oman": "OMN", "bahrain": "BHR",
                "united kingdom": "GBR", "uk": "GBR", "united states": "USA", "usa": "USA", "philippines": "PHL", "egypt": "EGY", "china": "CHN"}


def iso3(name: str | None) -> str:
    n = (name or "").strip()
    if re.fullmatch(r"[A-Za-z]{3}", n):
        return n.upper()
    low = n.lower()
    if low in COUNTRY_ISO3:
        return COUNTRY_ISO3[low]
    for part in reversed([p.strip().lower() for p in n.split(",")]):
        if part in COUNTRY_ISO3:
            return COUNTRY_ISO3[part]
    return ""


# ------------------------------------------------------------------ normalisation
def _upsert(db: Session, lid: str, **f) -> m.LifeObservation:
    ts = now_iso()
    row = db.get(m.LifeObservation, lid)
    if row is None:
        row = m.LifeObservation(id=lid, created_at=ts, updated_at=ts, **f)
        db.add(row)
    else:
        for k, v in f.items():
            setattr(row, k, v)
        row.updated_at = ts
    return row


def normalize_un_wpp(db: Session, observations: list[Observation]) -> int:
    n = 0
    for o in observations:
        r = o.raw
        _upsert(db, "LO:" + o.obs_key, external_observation_id=o.obs_key, domain=r["domain"], metric=o.indicator_code, metric_label=o.indicator_name,
                value=str(o.value), unit=o.unit, country=o.country_code.upper(), region=None, geo_level="NATIONAL", year=o.year, age=r.get("age"),
                age_group=r.get("ageGroup") or r.get("age"), sex=r.get("sex"), population_scope=f"{o.country_name}, whole population" + (f" ({r['sex'].lower()})" if r.get("sex") else ""),
                observation_type="PROJECTION" if r.get("projection") else "ESTIMATE", provider=o.provider, dataset=o.dataset,
                source=o.dataset, source_organization=o.source_organization, notes=o.source_note)
        n += 1
    return n


def normalize_world_bank(db: Session, observations: list[Observation]) -> int:
    from app.providers.world_bank import LIFE_MAP
    n = 0
    for o in observations:
        mp = LIFE_MAP.get(o.indicator_code)
        if not mp:
            continue
        oid = o.obs_key or f"{o.provider}:{o.indicator_code}:{o.country_code.upper()}:{o.year}"
        _upsert(db, "LO:" + oid, external_observation_id=oid, domain=mp["domain"], metric=mp["metric"], metric_label=o.indicator_name, value=str(o.value),
                unit=o.unit, country=o.country_code.upper(), region=None, geo_level="NATIONAL", year=o.year, sex=mp["sex"], education_level=mp["level"],
                age_group="65+" if mp["level"] == "65+" else None, population_scope=f"{o.country_name}, national", observation_type="ESTIMATE",
                provider=o.provider, dataset=o.dataset, source=o.dataset, source_organization=o.source_organization, notes=o.source_note[:500])
        n += 1
    return n


def life_obs_out(r: m.LifeObservation) -> dict:
    return {"id": r.id, "externalObservationId": r.external_observation_id, "domain": r.domain, "metric": r.metric, "metricLabel": r.metric_label,
            "value": r.value, "unit": r.unit, "country": r.country, "region": r.region, "geoLevel": r.geo_level, "year": r.year, "age": r.age,
            "ageGroup": r.age_group, "sex": r.sex, "educationLevel": r.education_level, "urbanRural": r.urban_rural, "incomeGroup": r.income_group,
            "householdType": r.household_type, "housingType": r.housing_type, "category": r.category, "originCountry": r.origin_country,
            "destinationCountry": r.destination_country, "currency": r.currency, "populationScope": r.population_scope,
            "observationType": r.observation_type, "provider": r.provider, "dataset": r.dataset, "source": r.source,
            "sourceOrganization": r.source_organization, "isPrototype": r.is_prototype, "notes": r.notes, "updatedAt": r.updated_at,
            "statisticKind": "POPULATION_STATISTIC"}


# ------------------------------------------------------------------ structured import (MoSPI / UAE / manual)
IMPORT_HEADER = ["domain", "metric", "metric_label", "value", "unit", "country", "year", "geo_level", "region", "sex", "age_group", "education_level",
                 "urban_rural", "income_group", "household_type", "housing_type", "category", "origin_country", "destination_country", "currency",
                 "population_scope", "observation_type", "source", "source_organization", "source_url", "notes"]
IMPORT_REQUIRED = ("domain", "metric", "value", "unit", "country", "year", "source", "source_organization")


def parse_life_import(text: str, provider: str) -> dict:
    import csv
    import io
    rows, errors = [], []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    hdr = [h.strip() for h in (reader.fieldnames or [])]
    missing_cols = [c for c in IMPORT_REQUIRED if c not in hdr]
    if missing_cols:
        return {"rows": [], "errors": [f"Missing required column(s): {', '.join(missing_cols)}"], "valid": 0, "header": IMPORT_HEADER}
    for i, raw in enumerate(reader, start=2):
        r = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        errs = [f"{c} is required" for c in IMPORT_REQUIRED if not r.get(c)]
        if r.get("domain") and r["domain"] not in DATA_DOMAINS:
            errs.append(f"domain must be one of {', '.join(DATA_DOMAINS)}")
        try:
            Decimal(r.get("value", "").replace(",", ""))
        except InvalidOperation:
            errs.append("value is not a number (missing values must be omitted, never estimated)")
        try:
            y = int(r.get("year") or 0)
            if not 1800 <= y <= 2100:
                errs.append("year out of range")
        except ValueError:
            errs.append("year is not an integer")
        c3 = iso3(r.get("country"))
        if not c3:
            errs.append("country must be an ISO3 code")
        gl = (r.get("geo_level") or ("CITY" if r.get("region") else "NATIONAL")).upper()
        if gl not in ("NATIONAL", "REGION", "CITY"):
            errs.append("geo_level must be NATIONAL, REGION or CITY")
        if gl != "NATIONAL" and not r.get("region"):
            errs.append("region is required for REGION/CITY rows")
        rows.append({"line": i, "row": {**r, "country": c3, "geo_level": gl}, "errors": errs})
    return {"rows": rows, "errors": [], "valid": sum(1 for x in rows if not x["errors"]), "header": IMPORT_HEADER, "provider": provider}


def commit_life_import(db: Session, text: str, provider: str, provider_name: str) -> dict:
    from app.services import truth
    pre = parse_life_import(text, provider)
    obs, kept = [], []
    for x in pre["rows"]:
        if x["errors"]:
            continue
        r = x["row"]
        key_bits = [r["domain"], r["metric"], r["country"], r.get("region") or "", r.get("sex") or "", r.get("age_group") or "", r.get("urban_rural") or "",
                    r.get("income_group") or "", r.get("category") or "", r.get("origin_country") or "", r.get("destination_country") or "", r["year"]]
        okey = f"{provider}:" + ":".join(re.sub(r"[^A-Za-z0-9_.\-]", "_", b) for b in key_bits)
        o = Observation(provider=provider, dataset=f"{provider_name} — structured import", indicator_code=f"{r['domain']}.{r['metric']}",
                        indicator_name=r.get("metric_label") or r["metric"], country_code=r["country"], country_name=r["country"], year=int(r["year"]),
                        value=Decimal(r["value"].replace(",", "")), unit=r["unit"], source_organization=r["source_organization"], source_note=r.get("notes", ""),
                        source_url=r.get("source_url", ""), raw={"import": True, "row": r}, obs_key=okey[:160])
        obs.append(o)
        kept.append((o, r))
    counts = truth.store_observations(db, obs)
    db.flush()
    for o, r in kept:
        _upsert(db, "LO:" + o.obs_key, external_observation_id=o.obs_key, domain=r["domain"], metric=r["metric"], metric_label=r.get("metric_label") or r["metric"],
                value=str(o.value), unit=r["unit"], country=r["country"], region=r.get("region") or None, geo_level=r["geo_level"], year=int(r["year"]),
                age_group=r.get("age_group") or None, sex=(r.get("sex") or "").upper() or None, education_level=r.get("education_level") or None,
                urban_rural=(r.get("urban_rural") or "").upper() or None, income_group=r.get("income_group") or None,
                household_type=r.get("household_type") or None, housing_type=r.get("housing_type") or None, category=r.get("category") or None,
                origin_country=iso3(r.get("origin_country")) or None, destination_country=iso3(r.get("destination_country")) or None,
                currency=r.get("currency") or None, population_scope=r.get("population_scope") or "", observation_type=(r.get("observation_type") or "SURVEY").upper(),
                provider=provider, dataset=o.dataset, source=r["source"], source_organization=r["source_organization"], notes=r.get("notes", ""))
    db.commit()
    return {**pre, "committed": len(kept), **counts, "rows": pre["rows"][:500]}


# ------------------------------------------------------------------ temporal coverage
def coverage_for_years(years: list[int], evidence: dict[int, list], window: int, derived_years: set[int] | None = None,
                       assumed_years: set[int] | None = None, projected_years: set[int] | None = None) -> list[dict]:
    """Per-year coverage. evidence = {sourceYear: [ids]}. Extending beyond the window is NOT allowed."""
    derived_years, assumed_years, projected_years = derived_years or set(), assumed_years or set(), projected_years or set()
    out = []
    ev_years = sorted(evidence)
    for y in years:
        if y in evidence and y not in projected_years:
            out.append({"year": y, "coverage": "DIRECT", "sourceYear": y, "distance": 0})
            continue
        near = sorted((abs(y - e), e) for e in ev_years if abs(y - e) <= window and e not in projected_years)
        if near and window > 0:
            out.append({"year": y, "coverage": "NEARBY", "sourceYear": near[0][1], "distance": near[0][0]})
        elif y in derived_years or y in projected_years:
            out.append({"year": y, "coverage": "DERIVED", "sourceYear": y, "distance": 0,
                        "note": "UN model projection" if y in projected_years else "stored derived calculation"})
        elif y in assumed_years:
            out.append({"year": y, "coverage": "ASSUMED", "sourceYear": None, "distance": None})
        else:
            closest = min(ev_years, key=lambda e: abs(e - y)) if ev_years else None
            out.append({"year": y, "coverage": "MISSING", "sourceYear": None, "distance": None,
                        "closestEvidenceYear": closest, "note": "Outside validity window — extension without methodology is not allowed" if closest else "No evidence"})
    return out


# ------------------------------------------------------------------ evidence match score (NOT probability)
def match_score(target: dict, o: m.LifeObservation, window: int, matrix_domain: str) -> dict:
    parts = []

    def add(dim, pts, mx, note):
        parts.append({"dimension": dim, "points": pts, "max": mx, "note": note})

    country_ok = o.country == target.get("country")
    add("country", 30 if country_ok else 0, 30, "match" if country_ok else f"{o.country} ≠ {target.get('country')}")
    d = abs(o.year - target["year"])
    yp = round(25 * max(0.0, 1 - d / (window + 1))) if window else (25 if d == 0 else 0)
    add("year", yp, 25, f"{d} year(s) from target" + (" — outside validity window" if d > window else ""))
    city = (target.get("city") or "").lower()
    if o.geo_level != "NATIONAL" and o.region and city and o.region.lower().startswith(city):
        add("geography", 10, 10, f"{o.geo_level.lower()} evidence for {o.region}")
    elif o.geo_level == "NATIONAL":
        sens = matrix_domain in GEO_SENSITIVE and bool(city)
        add("geography", 4 if sens else 10, 10, "national evidence for a city target — geographic mismatch" if sens else "national population statistic")
    else:
        add("geography", 2, 10, f"different sub-national area ({o.region})")
    for dim, key, mx, tv in (("sex", "sex", 10, target.get("sex")), ("urban/rural", "urban_rural", 5, target.get("urbanRural")),
                             ("income group", "income_group", 5, target.get("incomeGroup"))):
        v = getattr(o, key)
        if v is None:
            add(dim, mx // 2, mx, "not split by this dimension in the source")
        elif tv and v.upper() == str(tv).upper():
            add(dim, mx, mx, "match")
        else:
            add(dim, 0, mx, f"source population {v} ≠ target {tv or 'unspecified'}")
    q = 0 if o.is_prototype else (15 if o.provider in OFFICIAL_PROVIDERS else 9)
    add("source quality", q, 15, "PROTOTYPE — unusable" if o.is_prototype else ("official statistics" if q == 15 else "manual entry with named source"))
    return {"score": sum(p["points"] for p in parts), "breakdown": parts, "yearDistance": d, "countryMatch": country_ok,
            "label": "Evidence Match Score (not a probability)"}


# ------------------------------------------------------------------ life-stage plan (geography per year)
def stage_plan(db: Session, episode_id: str) -> dict:
    ep = db.get(m.Episode, episode_id)
    if ep is None or ep.character is None:
        raise LookupError(episode_id)
    ch = ep.character
    b = ch.birth_year
    origin = iso3(ch.country)
    city = re.sub(r"\s*\(.*\)", "", ch.region or "").strip()
    events = sorted(db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.episode_id == episode_id)), key=lambda e: e.year)
    moves = []  # (year, country, city)
    cur = origin
    for e in events:
        if e.category != "Migration":
            continue
        c = iso3(e.location)
        if c and c != cur:
            moves.append((e.year, c, (e.location or "").split(",")[0].strip()))
            cur = c

    def loc(y: int) -> tuple[str, str]:
        c, ct = origin, city
        for yr, cc, cty in moves:
            if y >= yr:
                c, ct = cc, cty
        return c, ct

    def first(cat, rx):
        for e in events:
            if e.category == cat and re.search(rx, e.title or "", re.I):
                return e.year
        return None

    job = first("Career", r"job|work|employ") or b + 20
    marriage = first("Relationships", r"marri")
    child = first("Family", r"child")
    retire = first("Career", r"retire") or b + 60
    mig_out = next(((y, c) for y, c, _ in moves if c != origin), None)
    plan = []

    def add(key, y0, y1, basis, applicable=True):
        plan.append({"stage": key, "label": STAGE_LABEL[key], "yearStart": y0, "yearEnd": y1, "basis": basis, "applicable": applicable})

    add("birth", b, b, "Character DNA birth year")
    add("childhood", b + 1, b + 5, "Ages 1–5")
    add("school", b + 6, b + 17, "Ages 6–17")
    add("higher-education", b + 18, b + 21, "Ages 18–21")
    add("first-job", job, job + 2, "Timeline first-job event" if first("Career", r"job|work|employ") else "Default age 20")
    if marriage:
        add("marriage-family", marriage, marriage + 2, "Timeline marriage event")
    else:
        add("marriage-family", b + 22, b + 32, "Default age window 22–32 (no marriage in timeline)")
    if mig_out:
        add("migration", mig_out[0] - 2, mig_out[0], f"Timeline move to {mig_out[1]} (two years before the move included)")
    else:
        add("migration", b, b, "No migration in timeline", applicable=False)
    add("mid-career", b + 35, b + 49, "Ages 35–49")
    if child:
        add("children-education", child + 5, child + 21, "Timeline first child + school/college years")
    else:
        add("children-education", b, b, "No child in timeline", applicable=False)
    add("late-career", b + 50, retire - 1, "Age 50 to retirement")
    add("retirement", retire, retire + 2, "Timeline retirement event" if first("Career", r"retire") else "Default age 60")
    add("old-age", retire + 3, b + 85, "After retirement to age 85")
    add("death", b + 60, b + 90, "Mortality evidence across ages 60–90 (death year is not predetermined)")
    for p in plan:
        locs = [loc(y) for y in range(p["yearStart"], p["yearEnd"] + 1)]
        p["countries"] = sorted({c for c, _ in locs if c})
        p["cities"] = sorted({ct for _, ct in locs if ct})
    return {"episodeId": episode_id, "birthYear": b, "origin": origin, "moves": [{"year": y, "country": c, "city": ct} for y, c, ct in moves],
            "stages": plan, "loc": loc, "character": {"sex": "MALE" if (ch.gender or "").lower().startswith("m") else "FEMALE" if (ch.gender or "").lower().startswith("f") else None,
                                                      "urbanRural": (ch.settlement or "").upper() or None, "incomeGroup": ch.starting_class or None}}


def plan_out(plan: dict) -> dict:
    return {k: v for k, v in plan.items() if k != "loc"}


# ------------------------------------------------------------------ events
def _date_year(d: str | None) -> int | None:
    return int(d[:4]) if d and re.match(r"^\d{4}", d) else None


def event_relevance(ev: m.HistoricalEvent, country: str, city: str, y0: int, y1: int) -> dict:
    es, ee = _date_year(ev.start_date), _date_year(ev.end_date) or _date_year(ev.start_date)
    overlap = es is not None and es <= y1 and (ee or es) >= y0
    geo = set(ev.geography or [])
    in_geo = "WORLD" in geo or country in geo or any(country in REGION_GROUPS.get(g, set()) for g in geo)
    if not overlap:
        return {"relevance": "NOT_RELEVANT", "reason": f"Event period {ev.start_date}–{ev.end_date or ''} does not overlap {y0}–{y1}"}
    if not in_geo:
        return {"relevance": "NOT_RELEVANT", "reason": f"Event geography {', '.join(sorted(geo))} does not include {country}"}
    if ev.region and city and not ev.region.lower().startswith(city.lower()):
        return {"relevance": "POSSIBLY_RELEVANT", "reason": f"Event limited to {ev.region}; character in {city}"}
    scope = "global" if "WORLD" in geo else country
    return {"relevance": "RELEVANT", "reason": f"Character in {city or country} during {max(es, y0)}–{min(ee or es, y1)}; event scope {scope}"}


def event_out(e: m.HistoricalEvent) -> dict:
    return {"id": e.id, "name": e.name, "category": e.category, "geography": e.geography, "region": e.region, "startDate": e.start_date,
            "endDate": e.end_date, "economicRelevance": e.economic_relevance, "description": e.description, "sources": e.sources,
            "verification": e.verification, "updatedAt": e.updated_at}


def policy_out(p: m.PolicyEvidence) -> dict:
    return {"id": p.id, "country": p.country, "policyType": p.policy_type, "title": p.title, "effectiveStart": p.effective_start, "effectiveEnd": p.effective_end,
            "description": p.description, "source": p.source, "sourceOrganization": p.source_organization, "sourceUrl": p.source_url,
            "factType": p.fact_type, "confidence": p.confidence, "verification": p.verification, "notes": p.notes, "updatedAt": p.updated_at}


def context_out(c: m.ContextEvidence) -> dict:
    return {"id": c.id, "topic": c.topic, "country": c.country, "region": c.region, "yearStart": c.year_start, "yearEnd": c.year_end,
            "populationScope": c.population_scope, "claim": c.claim, "source": c.source, "sourceUrl": c.source_url, "evidenceType": c.evidence_type,
            "confidence": c.confidence, "notes": c.notes, "dataKind": "QUALITATIVE_CONTEXT" if c.evidence_type != "MEASURABLE_CLAIM" else "MEASURABLE_CLAIM",
            "updatedAt": c.updated_at}


def assumption_out(a: m.Assumption, snap_ids: list[str] | None = None) -> dict:
    return {"id": a.id, "episodeId": a.episode_id, "kind": "register", "domain": a.domain, "lifeStage": a.life_stage, "claim": a.claim, "value": a.value,
            "unit": a.unit, "yearStart": a.year_start, "yearEnd": a.year_end, "reason": a.reason, "createdBy": a.created_by, "createdAt": a.created_at,
            "supportingEvidence": a.supporting_evidence, "confidence": a.confidence, "status": a.status, "includedInSnapshots": snap_ids or []}


def _policy_years(p: m.PolicyEvidence) -> tuple[int, int]:
    return _date_year(p.effective_start) or 0, _date_year(p.effective_end) or 2100


# ------------------------------------------------------------------ matrix
def _final_snapshot_records(db: Session, record_type: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    q = select(m.SnapshotRecord.record_id, m.SnapshotRecord.snapshot_id).join(m.EpisodeDatasetSnapshot, m.EpisodeDatasetSnapshot.id == m.SnapshotRecord.snapshot_id) \
        .where(m.SnapshotRecord.record_type == record_type, m.EpisodeDatasetSnapshot.status == "final")
    for rid, sid in db.execute(q):
        out.setdefault(rid, []).append(sid)
    return out


def life_matrix(db: Session, episode_id: str, with_detail: bool = False) -> dict:
    from app.services import labor
    plan = stage_plan(db, episode_id)
    loc = plan["loc"]
    countries = sorted({c for s in plan["stages"] for c in s["countries"]})
    L = m.LifeObservation
    # Life tables add ~22 age groups per country/sex/year; the matrix only needs one representative row (age 0) to show coverage.
    obs = list(db.scalars(select(L).where(L.country.in_(countries), or_(L.metric.notin_(["LT_QX", "LT_MX"]), and_(L.metric == "LT_QX", L.age == "0")))))
    wages = list(db.scalars(select(m.WageObservation).where(m.WageObservation.country.in_(countries))))
    econ = list(db.scalars(select(m.EconomicBaseline).where(m.EconomicBaseline.episode_id == episode_id)))
    lbs = list(db.scalars(select(m.LifeStageBaseline).where(m.LifeStageBaseline.episode_id == episode_id)))
    asms = [a for a in db.scalars(select(m.Assumption).where(m.Assumption.episode_id == episode_id)) if a.status == "active"]
    gaps = list(db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == episode_id)))
    events = list(db.scalars(select(m.HistoricalEvent)))
    policies = list(db.scalars(select(m.PolicyEvidence).where(m.PolicyEvidence.country.in_(countries))))
    contexts = list(db.scalars(select(m.ContextEvidence).where(m.ContextEvidence.country.in_(countries))))
    tasks = {t.id: t for t in db.scalars(select(m.ResearchTask).where(m.ResearchTask.episode_id == episode_id))}
    ch = plan["character"]
    econ_stage = {"first-job": "first-employment", "migration": "migration-wage", "mid-career": "migration-wage", "late-career": "migration-wage", "retirement": "retirement"}
    stages_out = []
    for st_key, st_label, critical, other in STAGES:
        sp = next(s for s in plan["stages"] if s["stage"] == st_key)
        years = list(range(sp["yearStart"], sp["yearEnd"] + 1))
        cells = []
        for dom in critical + other:
            window = WINDOW_FOR[dom]
            cell = {"domain": dom, "label": MATRIX_LABEL[dom], "critical": dom in critical, "windowYears": window, "windowReason": WINDOW_REASON.get(
                {"marriage": "family_formation", "household_spending": "household_expenditure", "historical": "context"}.get(dom, dom), "")}
            reasons: list[str] = []
            supporting, candidates, extra = [], [], []
            if not sp["applicable"]:
                cell.update(status="NOT_APPLICABLE", reasons=[sp["basis"]], coverage=[])
                cells.append(cell)
                continue
            asm = [a for a in asms if a.life_stage == st_key and a.domain == dom]
            assumed_years = {y for a in asm for y in years if (a.year_start or years[0]) <= y <= (a.year_end or years[-1])}
            if dom == "historical":
                rel = []
                for e in events:
                    best = None
                    for y in (years[0], years[len(years) // 2], years[-1]):
                        c, ct = loc(y)
                        r = event_relevance(e, c, ct, years[0], years[-1])
                        if best is None or ["NOT_RELEVANT", "POSSIBLY_RELEVANT", "RELEVANT"].index(r["relevance"]) > ["NOT_RELEVANT", "POSSIBLY_RELEVANT", "RELEVANT"].index(best["relevance"]):
                            best = r
                    if best and best["relevance"] != "NOT_RELEVANT":
                        rel.append({**event_out(e), **best})
                supporting = rel
                verified = [x for x in rel if x["relevance"] == "RELEVANT" and x["verification"] == "verified"]
                status = "READY" if verified else "PARTIAL" if rel else "MISSING"
                reasons.append(f"{len(rel)} relevant event(s) in registry" + ("" if verified else "; none verified by a human yet" if rel else
                                                                                   " — absence of registered events is not evidence that nothing happened"))
                cov = []
            elif dom == "income":
                ew = {}
                for y in years:
                    c, _ = loc(y)
                    for w in wages:
                        if w.country == c and abs(w.year - y) <= window:
                            ew.setdefault(w.year, []).append(w.id)
                cov = coverage_for_years(years, {k: v for k, v in ew.items()}, window, assumed_years=assumed_years)
                bl = [b for b in econ if b.life_stage == econ_stage.get(st_key) and b.year_start <= years[-1] and b.year_end >= years[0]]
                for b in bl:
                    tc = labor.wage_anchor_coverage(b)
                    supporting.append({"type": "economic-baseline", "id": b.id, "label": f"{b.baseline_type} {b.point or (b.low or '') + '–' + (b.high or '')} {b.currency}/{b.pay_period.lower()}",
                                       "approved": b.user_approved, "anchors": tc["directCoverage"], "unresolvedYears": tc["unresolvedYears"]})
                n_wage_years = sorted(ew)
                if n_wage_years:
                    supporting.append({"type": "wage-observations", "label": f"Wage observations in years {', '.join(map(str, n_wage_years))}", "count": sum(len(v) for v in ew.values())})
                covered = [c for c in cov if c["coverage"] in ("DIRECT", "NEARBY")]
                approved = any(b.user_approved for b in bl)
                if approved and len(covered) == len(years):
                    status = "READY"
                elif covered or bl or assumed_years:
                    status = "PARTIAL"
                else:
                    status = "MISSING"
                if bl:
                    reasons.append(f"{len(bl)} economic baseline(s) overlap; wage anchors are direct evidence only for their own year(s)")
                reasons.append(f"{len(covered)}/{len(years)} year(s) have wage evidence within ±{window} year")
            else:
                srcs = MATRIX_SOURCES[dom]
                ev_years: dict[int, list] = {}
                proj: set[int] = set()
                best_by_id: dict[str, dict] = {}
                geo_mismatch = False
                for y in years:
                    c, ct = loc(y)
                    tgt = {"country": c, "city": ct, "year": y, **ch}
                    for o in obs:
                        if o.domain not in srcs or o.country != c or o.is_prototype:
                            continue
                        dist = abs(o.year - y)
                        if dist <= window:
                            if o.observation_type == "PROJECTION":
                                if o.year == y:
                                    proj.add(y)
                                    ev_years.setdefault(y, [])
                            else:
                                ev_years.setdefault(o.year, []).append(o.id)
                            if o.id not in best_by_id and len(best_by_id) < 400:
                                sc = match_score(tgt, o, window, dom)
                                best_by_id[o.id] = {**life_obs_out(o), "match": sc}
                                if dom in GEO_SENSITIVE and o.geo_level == "NATIONAL" and ct:
                                    geo_mismatch = True
                        elif with_detail and dist <= window + 15 and len(candidates) < 8 and all(x["id"] != o.id for x in candidates):
                            candidates.append({**life_obs_out(o), "match": match_score(tgt, o, window, dom), "outsideWindow": True})
                proj -= {y for y in ev_years if ev_years[y]}
                cov = coverage_for_years(years, {k: v for k, v in ev_years.items() if v or k in proj}, window, assumed_years=assumed_years, projected_years=proj)
                supporting = sorted(best_by_id.values(), key=lambda x: -x["match"]["score"])
                lb = [b for b in lbs if b.life_stage == st_key and b.domain in srcs + [dom]]
                for b in lb:
                    extra.append({"type": "life-baseline", "id": b.id, "approved": b.user_approved, "coverageType": b.coverage_type})
                counts = {k: sum(1 for c in cov if c["coverage"] == k) for k in ("DIRECT", "NEARBY", "DERIVED", "ASSUMED", "MISSING")}
                if any(b.user_approved for b in lb) and not counts["MISSING"]:
                    status = "READY"
                elif counts["MISSING"] == 0 and counts["DIRECT"] + counts["NEARBY"] + counts["DERIVED"] == len(years) and not geo_mismatch and counts["DIRECT"] > 0:
                    status = "READY"
                elif counts["MISSING"] == 0 and counts["DERIVED"] and not geo_mismatch and counts["DIRECT"] + counts["NEARBY"] + counts["DERIVED"] == len(years):
                    status = "READY"
                elif counts["MISSING"] < len(years):
                    status = "PARTIAL"
                else:
                    status = "MISSING"
                reasons.append(", ".join(f"{v} {k}" for k, v in counts.items() if v) + f" of {len(years)} year(s) (window ±{window})")
                if geo_mismatch:
                    reasons.append("Only national evidence for a city-level need — capped at PARTIAL")
                if counts["DERIVED"]:
                    reasons.append("DERIVED years rely on UN model projections, not observations")
                if dom in ("marriage", "fertility", "mortality"):
                    reasons.append("Population statistic — not the character's outcome")
            if dom in ("migration", "retirement"):
                ptypes = {"migration": {"work-visa", "residency", "citizenship", "family-sponsorship", "emigration", "labour-law"},
                          "retirement": {"retirement", "pension", "labour-law"}}[dom]
                for p in policies:
                    py0, py1 = _policy_years(p)
                    if p.policy_type in ptypes and p.country in {loc(y)[0] for y in years} | ({plan["origin"]} if dom == "migration" else set()) and py0 <= years[-1] and py1 >= years[0]:
                        extra.append({"type": "policy", **policy_out(p)})
            ctx = [context_out(c) for c in contexts if c.country in {loc(y)[0] for y in years} and c.year_start <= years[-1] and c.year_end + 10 >= years[0]
                   and (c.topic in {"marriage": ("marriage-norms", "family-expectations", "gender-roles"), "migration": ("migration-attitudes",),
                                    "household_spending": ("multi-generational-households", "social-status")}.get(dom, ()))]
            extra += [{"type": "context", **c} for c in ctx]
            cell_gaps = [g for g in gaps if g.gap_key == f"life:{st_key}:{dom}" or (g.life_stage == st_key and g.domain == dom)]
            ev_n = sum(1 for c in cov if c["coverage"] in ("DIRECT", "NEARBY", "DERIVED"))
            as_n = sum(1 for c in cov if c["coverage"] == "ASSUMED")
            ev_status = "MISSING" if not cov or ev_n == 0 else "VERIFIED" if ev_n == len(cov) and status == "READY" else "PARTIALLY VERIFIED"
            sim_status = ev_status if ev_status == "VERIFIED" else ("ASSUMPTION-COVERED" if ev_status == "MISSING" and as_n else
                                                                     "PARTIALLY VERIFIED" if ev_status != "MISSING" else "MISSING")
            if status == "NOT_APPLICABLE":
                ev_status = sim_status = "NOT_APPLICABLE"
            cell.update(evidenceStatus=ev_status, simulationStatus=sim_status, assumedYears=as_n)
            cell.update(status=status, reasons=reasons, coverage=cov,
                        counts={k: sum(1 for c in cov if c["coverage"] == k) for k in ("DIRECT", "NEARBY", "DERIVED", "ASSUMED", "MISSING")},
                        supportingCount=len(supporting), assumptionCount=len(asm), gapCount=sum(1 for g in cell_gaps if g.status == "open"))
            if with_detail:
                from app.services.labor import gap_out
                cell.update(supporting=supporting[:60], candidates=sorted(candidates, key=lambda x: -x["match"]["score"])[:8], extra=extra,
                            assumptions=[assumption_out(a) for a in asm], gaps=[gap_out(g) for g in cell_gaps],
                            researchTasks=[{"id": t.id, "question": t.question, "status": t.status} for g in cell_gaps if g.research_task_id
                                           for t in [tasks.get(g.research_task_id)] if t])
            cells.append(cell)
        crit = [c for c in cells if c["critical"] and c["status"] != "NOT_APPLICABLE"]
        if not sp["applicable"]:
            sst = "NOT_APPLICABLE"
        elif crit and all(c["status"] == "READY" for c in crit):
            sst = "READY"
        elif crit and all(c["status"] == "MISSING" for c in crit):
            sst = "MISSING"
        else:
            sst = "PARTIAL"
        stages_out.append({**{k: v for k, v in sp.items()}, "status": sst, "cells": cells})
    return {"plan": plan_out(plan), "stages": stages_out, "domains": [{"key": k, "label": v} for k, v, _ in MATRIX_DOMAINS],
            "windows": {k: {"years": WINDOW_FOR[k]} for k in WINDOW_FOR},
            "note": "Coverage measures whether evidence exists. Evidence Match Scores are not probabilities; population statistics are not individual outcomes."}


def readiness_v2(db: Session, episode_id: str, required: list[str]) -> dict:
    mx = life_matrix(db, episode_id)
    groups = []
    for key, label, doms in READINESS_GROUPS:
        cells = [(s["stage"], c) for s in mx["stages"] for c in s["cells"] if c["domain"] in doms and c["status"] != "NOT_APPLICABLE"]
        if not cells:
            st = "NOT_APPLICABLE"
        elif all(c["status"] == "READY" for _, c in cells):
            st = "READY"
        elif all(c["status"] == "MISSING" for _, c in cells):
            st = "NOT_READY"
        else:
            st = "PARTIAL"
        groups.append({"key": key, "label": label, "status": st, "required": key in required,
                       "cells": [{"stage": s, "domain": c["domain"], "status": c["status"]} for s, c in cells],
                       "ready": sum(1 for _, c in cells if c["status"] == "READY"), "partial": sum(1 for _, c in cells if c["status"] == "PARTIAL"),
                       "missing": sum(1 for _, c in cells if c["status"] == "MISSING")})
    req = [g for g in groups if g["required"] and g["status"] != "NOT_APPLICABLE"]
    crit_missing = [f"{s['label']}: {c['label']}" for s in mx["stages"] for c in s["cells"]
                    if c["critical"] and c["status"] == "MISSING" and any(c["domain"] in d for k, _, d in READINESS_GROUPS if k in required)]
    if any(g["status"] == "NOT_READY" for g in req) or crit_missing:
        overall = "NOT_READY"
    elif all(g["status"] == "READY" for g in req):
        overall = "READY"
    else:
        overall = "PARTIAL"
    return {"overall": overall, "groups": groups, "required": required, "blocking": crit_missing,
            "stages": [{"stage": s["stage"], "label": s["label"], "status": s["status"]} for s in mx["stages"]],
            "note": "Evidence availability only — not statistical confidence. A simulation must not proceed silently while required domains are missing; "
                    "missing domains may later be overridden only by explicit assumptions."}


def detect_life_gaps(db: Session, episode_id: str, required: list[str]) -> list[m.EvidenceGap]:
    mx = life_matrix(db, episode_id)
    plan = mx["plan"]
    ch = plan["character"]
    req_domains = {d for k, _, ds in READINESS_GROUPS if k in required for d in ds}
    found = {}
    for s in mx["stages"]:
        for c in s["cells"]:
            if c["status"] not in ("MISSING",) and not (c["status"] == "PARTIAL" and c["critical"] and c["domain"] in GEO_SENSITIVE | {"income"}):
                continue
            if not c["critical"] and c["domain"] != "historical":
                continue
            place = "/".join(s.get("cities") or []) or "/".join(s["countries"])
            pop = ", ".join(x for x in [(ch.get("sex") or "").lower(), (ch.get("urbanRural") or "").lower(), (ch.get("incomeGroup") or "") + " household"] if x.strip())
            missing_years = [x["year"] for x in c["coverage"] if x["coverage"] == "MISSING"]
            found[f"life:{s['stage']}:{c['domain']}"] = dict(
                title=f"{s['label']} · {MATRIX_LABEL[c['domain']]}: {place} {s['yearStart']}–{s['yearEnd']}",
                reason=f"Need {NEED[c['domain']]}. Status {c['status']}: " + "; ".join(c["reasons"]) + (f". Unresolved years: {missing_years[0]}–{missing_years[-1]}" if missing_years else ""),
                category=TASK_CAT[c["domain"]], country=", ".join(s["countries"]), year_start=s["yearStart"], year_end=s["yearEnd"],
                priority="HIGH" if c["critical"] and c["domain"] in req_domains and c["status"] == "MISSING" else "MEDIUM" if c["critical"] else "LOW",
                domain=c["domain"], life_stage=s["stage"], target_population=pop)
    ts = now_iso()
    existing = {g.gap_key: g for g in db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == episode_id))}
    for key, g in existing.items():
        if key.startswith("life:") and g.auto and key not in found and g.status == "open":
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
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(db.scalars(select(m.EvidenceGap).where(m.EvidenceGap.episode_id == episode_id)), key=lambda g: (g.status != "open", order.get(g.priority, 3), g.created_at))


# ------------------------------------------------------------------ life-stage baselines
class LifeError(ValueError):
    pass


def _dec(v) -> str | None:
    if v in (None, ""):
        return None
    try:
        return str(Decimal(str(v).replace(",", "")))
    except InvalidOperation as e:
        raise LifeError(f"Not a number: {v}") from e


def create_life_baseline(db: Session, episode_id: str, req: dict) -> m.LifeStageBaseline:
    dom = req["domain"]
    if dom not in DATA_DOMAINS or dom == "employment_context":
        raise LifeError("Unsupported baseline domain (income baselines use Employment Evidence)")
    st = req["lifeStage"]
    if st not in STAGE_LABEL:
        raise LifeError("Unknown life stage")
    y0, y1 = int(req["yearStart"]), int(req["yearEnd"])
    if y1 < y0:
        raise LifeError("yearEnd must be >= yearStart")
    plan = stage_plan(db, episode_id)
    loc = plan["loc"]
    obs = [db.get(m.LifeObservation, i) for i in req.get("lifeObservationIds", [])]
    if any(o is None for o in obs):
        raise LifeError("Unknown life observation")
    if any(o.is_prototype for o in obs):
        raise LifeError("PROTOTYPE observations cannot support a baseline")
    if any(o.domain != dom for o in obs):
        raise LifeError("All evidence must belong to the baseline domain")
    asms = [db.get(m.Assumption, i) for i in req.get("assumptionIds", [])]
    if any(a is None or a.episode_id != episode_id for a in asms):
        raise LifeError("Unknown assumption")
    if not obs and not asms:
        raise LifeError("A baseline needs selected evidence or an explicit assumption from the register")
    if len({o.unit for o in obs}) > 1:
        raise LifeError("Evidence mixes units; normalise explicitly first")
    window = VALIDITY_WINDOW[dom]
    years = list(range(y0, y1 + 1))
    ev = {}
    proj = set()
    for o in obs:
        if o.observation_type == "PROJECTION":
            proj.add(o.year)
        ev.setdefault(o.year, []).append(o.id)
    assumed = {y for a in asms for y in years if (a.year_start or y0) <= y <= (a.year_end or y1)}
    cov = coverage_for_years(years, ev, window, assumed_years=assumed, projected_years=proj)
    missing = [c["year"] for c in cov if c["coverage"] == "MISSING"]
    if missing:
        raise LifeError(f"Unsupported period extension: year(s) {', '.join(map(str, missing))} have no evidence within the ±{window}-year {dom} "
                        "validity window. Add evidence, an explicit assumption, or narrow the period.")
    kinds = {c["coverage"] for c in cov}
    ctype = "ASSUMED" if "ASSUMED" in kinds else "DERIVED" if "DERIVED" in kinds else "NEARBY" if "NEARBY" in kinds else "DIRECT"
    country = loc(y0)[0]
    city = loc(y0)[1]
    scores = [match_score({"country": loc(o.year if y0 <= o.year <= y1 else y0)[0], "city": city, "year": min(max(o.year, y0), y1), **plan["character"]}, o, window,
                          {"household_expenditure": "household_spending"}.get(dom, dom)) for o in obs]
    reasons = []
    if scores:
        avg = sum(s["score"] for s in scores) / len(scores)
        conf = "HIGH" if avg >= 80 else "MEDIUM" if avg >= 60 else "LOW"
    else:
        conf = "LOW"
    if ctype == "ASSUMED":
        conf = "LOW"
        reasons.append("Relies on explicit assumptions for some or all years")
    if dom in ("housing", "household_expenditure") and city and any(o.geo_level == "NATIONAL" for o in obs):
        conf = "LOW" if conf == "LOW" else "MEDIUM"
        reasons.append("National evidence used for a city-level stage — geographic mismatch")
    kind = (req.get("estimateKind") or "").upper()
    low, high, point = _dec(req.get("low")), _dec(req.get("high")), _dec(req.get("point"))
    dist = req.get("distribution")
    if not (low or high or point or dist):
        vals = sorted(Decimal(o.value) for o in obs)
        if not vals:
            raise LifeError("Give a point value, a range or a distribution")
        if len(vals) == 1:
            point = str(vals[0])
        else:
            low, high = str(vals[0]), str(vals[-1])
    kind = kind or ("DISTRIBUTION" if dist else "POINT" if point else "RANGE")
    if low and high and Decimal(high) < Decimal(low):
        raise LifeError("high must be >= low")
    ts = now_iso()
    b = m.LifeStageBaseline(id="LSB-" + uuid.uuid4().hex[:10], episode_id=episode_id, domain=dom, life_stage=st, year_start=y0, year_end=y1, country=country,
                            scope=req.get("scope") or f"{city or country}, {', '.join(x for x in [(plan['character'].get('sex') or '').lower()] if x)}",
                            metric=req.get("metric") or (obs[0].metric if obs else ""), estimate_kind=kind, low=low, high=high, point=point, distribution=dist,
                            unit=req.get("unit") or (obs[0].unit if obs else ""), coverage_type=ctype, coverage=cov, confidence=conf,
                            evidence=[{"lifeObservationId": o.id, "externalObservationId": o.external_observation_id, "year": o.year, "value": o.value,
                                       "score": s["score"], "observationType": o.observation_type} for o, s in zip(obs, scores)],
                            assumption_ids=[a.id for a in asms], reasoning=(req.get("reasoning") or "").strip() + (" " + " ".join(reasons) if reasons else ""),
                            user_approved=False, approved_at=None, created_at=ts, updated_at=ts)
    db.add(b)
    db.commit()
    return b


def life_baseline_out(b: m.LifeStageBaseline) -> dict:
    return {"id": b.id, "episodeId": b.episode_id, "domain": b.domain, "lifeStage": b.life_stage, "lifeStageLabel": STAGE_LABEL.get(b.life_stage, b.life_stage),
            "yearStart": b.year_start, "yearEnd": b.year_end, "country": b.country, "scope": b.scope, "metric": b.metric, "estimateKind": b.estimate_kind,
            "low": b.low, "high": b.high, "point": b.point, "distribution": b.distribution, "unit": b.unit, "coverageType": b.coverage_type,
            "coverage": b.coverage, "confidence": b.confidence, "evidence": b.evidence, "assumptionIds": b.assumption_ids, "reasoning": b.reasoning,
            "userApproved": b.user_approved, "approvedAt": b.approved_at, "createdAt": b.created_at,
            "note": "Population evidence summarised for a life stage — not the character's outcome."}


# ------------------------------------------------------------------ assumption register
def assumption_register(db: Session, episode_id: str) -> list[dict]:
    snap = _final_snapshot_records(db, "assumption")
    out = [assumption_out(a, snap.get(a.id)) for a in db.scalars(select(m.Assumption).where(m.Assumption.episode_id == episode_id).order_by(m.Assumption.created_at))]
    snap_f = {}
    for fid, sid in db.execute(select(m.SnapshotFact.fact_id, m.SnapshotFact.snapshot_id).join(m.EpisodeDatasetSnapshot, m.EpisodeDatasetSnapshot.id == m.SnapshotFact.snapshot_id)
                               .where(m.EpisodeDatasetSnapshot.status == "final", m.EpisodeDatasetSnapshot.episode_id == episode_id)):
        snap_f.setdefault(fid, []).append(sid)
    for f in db.scalars(select(m.Fact).where(m.Fact.episode_id == episode_id, m.Fact.fact_type == "ASSUMPTION")):
        out.append({"id": f.id, "episodeId": episode_id, "kind": "fact", "domain": f.category.lower(), "lifeStage": "", "claim": f.metric, "value": f.value,
                    "unit": f.unit, "yearStart": f.year_start, "yearEnd": f.year_end, "reason": f.notes, "createdBy": "user", "createdAt": f.created_at,
                    "supportingEvidence": [], "confidence": (f.confidence or "").upper(), "status": "prototype" if f.is_prototype else "active",
                    "includedInSnapshots": snap_f.get(f.id, []), "isPrototype": f.is_prototype})
    return out


# ------------------------------------------------------------------ migration path evidence
def migration_paths(db: Session, episode_id: str) -> list[dict]:
    plan = stage_plan(db, episode_id)
    paths = [(p.id, p.origin, p.destination, p.year_start, p.year_end, p.notes, False) for p in
             db.scalars(select(m.MigrationPath).where(m.MigrationPath.episode_id == episode_id))]
    prev = plan["origin"]
    for mv in plan["moves"]:
        if not any(p[1] == prev and p[2] == mv["country"] for p in paths):
            paths.append((f"auto:{prev}-{mv['country']}:{mv['year']}", prev, mv["country"], mv["year"] - 10, mv["year"], "Derived from timeline move", True))
        prev = mv["country"]
    out = []
    for pid, o, d, y0, y1, notes, auto in paths:
        ob = [life_obs_out(x) for x in db.scalars(select(m.LifeObservation).where(m.LifeObservation.domain == "migration", m.LifeObservation.country.in_([o, d]),
                                                                                    m.LifeObservation.year >= y0 - 3, m.LifeObservation.year <= y1 + 3)
                                                     .order_by(m.LifeObservation.country, m.LifeObservation.metric, m.LifeObservation.year))]
        pol = [policy_out(p) for p in db.scalars(select(m.PolicyEvidence).where(m.PolicyEvidence.country.in_([o, d])))
               if _policy_years(p)[0] <= y1 and _policy_years(p)[1] >= y0]
        wages = db.scalars(select(m.WageObservation.year).where(m.WageObservation.country == d, m.WageObservation.year >= y0, m.WageObservation.year <= y1 + 5)).all()
        bilateral = [x for x in ob if x["originCountry"] == o and x["destinationCountry"] == d]
        out.append({"id": pid, "origin": o, "destination": d, "yearStart": y0, "yearEnd": y1, "notes": notes, "auto": auto, "observations": ob,
                    "bilateralObservations": len(bilateral), "policies": pol, "destinationWageYears": sorted(set(wages)),
                    "missing": ([] if bilateral else [f"No bilateral {o}→{d} flow or migrant-stock statistics stored (e.g. UN DESA International Migrant Stock by origin — import required)"])
                    + ([] if wages else [f"No destination wage observations in {y0}–{y1 + 5}"]),
                    "note": "Net migration and migrant stock describe populations, not an individual's probability of emigrating. No probability is calculated."})
    return out
