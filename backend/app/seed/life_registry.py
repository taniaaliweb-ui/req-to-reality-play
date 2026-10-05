"""Reference registry entries (historical events, policy evidence) seeded once, idempotently.

Every entry is marked verification="unverified": dates and descriptions are widely documented, but a
human must check them against the cited organisation before they count as verified evidence.
No qualitative social-context claims are seeded — those require a real source and scope."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import models as m
from app.services.repository import now_iso

EVENTS = [
    ("EV-1973-OIL", "1973 oil crisis (OAPEC oil embargo)", "oil-shock", ["WORLD"], None, "1973-10", "1974-03", "HIGH",
     "Arab oil producers embargoed exports to several countries; crude prices roughly quadrupled. Gulf producer revenues rose sharply.", "IEA / IMF historical reviews"),
    ("EV-1975-EMERGENCY", "The Emergency in India", "policy-change", ["IND"], None, "1975-06-25", "1977-03-21", "MEDIUM",
     "National state of emergency proclaimed under Article 352; civil liberties suspended.", "Government of India records"),
    ("EV-1979-OIL", "1979 oil shock (Iranian revolution)", "oil-shock", ["WORLD"], None, "1979", "1980", "HIGH",
     "Oil supply disruption after the Iranian revolution; second major price spike of the 1970s.", "IEA / IMF historical reviews"),
    ("EV-1990-GULF", "Iraqi invasion of Kuwait and Gulf War", "war", ["KWT", "IRQ", "GCC", "IND"], None, "1990-08-02", "1991-02-28", "HIGH",
     "Invasion of Kuwait and subsequent war; large-scale evacuation of Indian workers from Kuwait in 1990; oil price spike.", "UN / Ministry of External Affairs (India)"),
    ("EV-1991-BOP", "India balance-of-payments crisis and economic liberalisation", "currency-crisis", ["IND"], None, "1991-06", "1993", "HIGH",
     "Foreign-exchange reserve crisis, rupee devaluation (July 1991) and start of liberalisation reforms.", "Reserve Bank of India / IMF"),
    ("EV-1997-AFC", "Asian financial crisis", "financial-crisis", ["THA", "IDN", "KOR", "MYS", "PHL"], None, "1997-07", "1998-12", "HIGH",
     "Currency and banking crises across East and Southeast Asia.", "IMF"),
    ("EV-2001-GUJARAT", "Gujarat earthquake", "natural-disaster", ["IND"], "Gujarat", "2001-01-26", "2001-01-26", "MEDIUM",
     "Major earthquake centred in Kutch district, Gujarat.", "Government of Gujarat / USGS"),
    ("EV-2008-GFC", "Global financial crisis", "financial-crisis", ["WORLD"], None, "2008-09", "2009-12", "HIGH",
     "Global banking crisis and recession following the collapse of Lehman Brothers.", "IMF World Economic Outlook"),
    ("EV-2009-DUBAI", "Dubai World debt standstill", "financial-crisis", ["ARE"], "Dubai", "2009-11-25", "2010", "HIGH",
     "Dubai World requested a standstill on debt repayments; property and construction downturn in Dubai.", "Government of Dubai / IMF Article IV"),
    ("EV-2014-OIL", "2014–2016 oil price collapse", "oil-shock", ["WORLD", "GCC"], None, "2014-06", "2016-02", "HIGH",
     "Brent crude fell by more than half; fiscal tightening across Gulf states.", "IMF / World Bank"),
    ("EV-2016-DEMON", "Indian banknote demonetisation", "policy-change", ["IND"], None, "2016-11-08", "2016-12-30", "MEDIUM",
     "₹500 and ₹1000 banknotes withdrawn as legal tender.", "Reserve Bank of India"),
    ("EV-2017-GST", "India Goods and Services Tax introduced", "policy-change", ["IND"], None, "2017-07-01", None, "MEDIUM",
     "Nationwide indirect tax replacing multiple central and state taxes.", "GST Council, Government of India"),
    ("EV-2018-VAT", "Value-added tax introduced in the UAE", "policy-change", ["ARE"], None, "2018-01-01", None, "MEDIUM",
     "5% VAT introduced.", "UAE Federal Tax Authority"),
    ("EV-2020-COVID", "COVID-19 pandemic", "pandemic", ["WORLD"], None, "2020-03-11", "2023-05-05", "HIGH",
     "WHO characterised COVID-19 as a pandemic on 11 March 2020; the global health emergency was declared over on 5 May 2023.", "World Health Organization"),
]

POLICIES = [
    ("POL-ARE-LABOUR-1980", "ARE", "labour-law", "UAE Federal Law No. 8 of 1980 regulating labour relations", "1980", "2022-02-01",
     "Private-sector labour law including end-of-service gratuity (21 days' basic wage per year for the first five years, 30 days per year thereafter, subject to conditions).",
     "UAE Ministry of Human Resources and Emiratisation"),
    ("POL-ARE-LABOUR-2021", "ARE", "labour-law", "UAE Federal Decree-Law No. 33 of 2021 on the regulation of labour relations", "2022-02-02", None,
     "Replaced Federal Law No. 8 of 1980 for the private sector; retains end-of-service gratuity.", "UAE Ministry of Human Resources and Emiratisation"),
    ("POL-IND-EMIG-1983", "IND", "emigration", "Emigration Act, 1983", "1983", None,
     "Regulates emigration of Indian workers; emigration clearance (ECR) required for certain categories travelling to notified countries, including the UAE.",
     "Ministry of External Affairs, Government of India"),
    ("POL-IND-EPF-1952", "IND", "pension", "Employees' Provident Funds and Miscellaneous Provisions Act, 1952", "1952", None,
     "Mandatory provident fund for employees of covered establishments.", "Employees' Provident Fund Organisation"),
    ("POL-IND-EPS-1995", "IND", "pension", "Employees' Pension Scheme, 1995", "1995-11-16", None,
     "Pension scheme for EPF members (part of employer contribution).", "Employees' Provident Fund Organisation"),
]


def seed_life_registry(db: Session) -> None:
    ts = now_iso()
    for eid, name, cat, geo, region, s, e, rel, desc, src in EVENTS:
        if db.get(m.HistoricalEvent, eid) is None:
            db.add(m.HistoricalEvent(id=eid, name=name, category=cat, geography=geo, region=region, start_date=s, end_date=e, economic_relevance=rel,
                                     description=desc, sources=[{"organization": src, "title": name, "url": ""}], verification="unverified",
                                     created_at=ts, updated_at=ts))
    for pid, c, t, title, s, e, desc, org in POLICIES:
        if db.get(m.PolicyEvidence, pid) is None:
            db.add(m.PolicyEvidence(id=pid, country=c, policy_type=t, title=title, effective_start=s, effective_end=e, description=desc, source=title,
                                    source_organization=org, source_url="", fact_type="FACT", confidence="MEDIUM", verification="unverified",
                                    notes="Seeded reference entry — verify against the official text before relying on it.", created_at=ts, updated_at=ts))
    db.commit()
