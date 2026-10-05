"""Life Receipt derived from canonical backend data (port of src/features/receipt/derive.ts).
Uses PROTOTYPE economic rows; no tax or real CPI model exists yet."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models as m


def derive_receipt(db: Session, episode_id: str) -> dict:
    ep = db.get(m.Episode, episode_id)
    if ep is None:
        raise LookupError(episode_id)
    events = sorted(db.scalars(select(m.TimelineEvent).where(m.TimelineEvent.episode_id == episode_id)), key=lambda e: e.year)
    econ = sorted(db.scalars(select(m.EconomicYear).where(m.EconomicYear.episode_id == episode_id)), key=lambda y: y.year)
    death = next((e for e in events if e.title.lower() == "death"), None)
    retire = next((e for e in events if re.search("retire", e.title, re.I)), None)
    first_job = next((e for e in events if e.category == "Career"), None)
    base = econ[0].price_index if econ else 100
    hh = lambda y: y.income + y.spouse_income  # noqa: E731
    nw = [y.assets + y.investments - y.liabilities for y in econ]
    end = nw[-1] if nw else 0
    born = ep.character.birth_year
    return {
        "episodeId": episode_id, "isPrototype": True,
        "born": born, "died": death.year if death else 0, "age": (death.year - born) if death else 0,
        "countries": list(dict.fromkeys(e.location.split(",")[-1].strip() for e in events)),
        "lifetimeNominal": round(sum(hh(y) for y in econ)),
        "lifetimeReal": round(sum(hh(y) * base / y.price_index for y in econ)),
        "housingSpent": round(sum(y.housing for y in econ)),
        "educationSpent": round(sum(y.education for y in econ)),
        "healthcareSpent": round(sum(y.healthcare for y in econ)),
        "peakNetWorth": max([0, *nw]), "netWorthAtDeath": end,
        "yearsWorking": ((retire or death).year if (retire or death) else 0) - (first_job.year if first_job else 0),
        "yearsRetired": (death.year - retire.year) if (retire and death) else 0,
        "startingClass": ep.character.starting_class,
        "endingClass": "upper-middle" if end > 8e6 else "middle" if end > 3e6 else ep.character.starting_class,
        "currency": econ[0].currency if econ else "INR",
        "note": "Prototype: ending class is a placeholder heuristic; taxes not modelled.",
    }
