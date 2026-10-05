"""Story engine (no AI): canonical run → chapters → story beats → structured local draft with claim provenance,
story audit, production workspace (scenes + script), Life Receipt 2.0 and source appendix.

Every narrative statement maps to FACTUAL_CONTEXT | DERIVED_DATA | SIMULATED_EVENT | ASSUMPTION | NARRATIVE_INTERPRETATION."""
from __future__ import annotations

import re
from decimal import Decimal

DRAFT_LABEL = "STRUCTURED LOCAL DRAFT — generated from simulation data without AI. All life events are SIMULATED."
CLAIM_TYPES = ("FACTUAL_CONTEXT", "DERIVED_DATA", "SIMULATED_EVENT", "ASSUMPTION", "NARRATIVE_INTERPRETATION")
COUNTRY_NAME = {"IND": "India", "ARE": "the UAE", "USA": "the United States", "GBR": "the United Kingdom", "PAK": "Pakistan", "BGD": "Bangladesh", "SAU": "Saudi Arabia"}

CHAPTERS = [
    ("birth", "Birth & Family"), ("childhood", "Childhood"), ("education", "Education"), ("work", "Entering Work"), ("family", "Marriage & Family"),
    ("children", "Children"), ("migration", "Migration"), ("career", "Career"), ("crisis", "Crisis / Opportunity"), ("middle", "Middle Age"),
    ("later", "Later Career"), ("retirement", "Retirement"), ("final", "Final Years"), ("death", "Death"), ("receipt", "Life Receipt"),
]
TITLE = dict(CHAPTERS)
TYPE_CHAPTER = {"birth": "birth", "enroll_primary": "childhood", "enter_secondary": "education", "enter_university": "education", "enter_vocational": "education",
                "complete_tertiary": "education", "complete_secondary": "education", "dropout": "education", "first_job": "work", "meet_partner": "family",
                "marriage": "family", "separation": "family", "divorce": "family", "widowhood": "family", "child_born": "children", "migration": "migration",
                "migration_opportunity": "migration", "failed_migration": "migration", "return_migration": "migration", "promotion": "career",
                "job_change": "career", "business_start": "career", "business_success": "crisis", "business_failure": "crisis", "job_loss": "crisis",
                "financial_distress": "crisis", "deprivation": "crisis", "forced_sale": "crisis", "inheritance": "crisis", "investment_windfall": "crisis",
                "career_breakthrough": "crisis", "major_asset_loss": "crisis", "purchase": "middle", "retirement": "retirement", "return_to_work": "retirement",
                "major_condition_onset": "final", "terminal_illness": "final", "disability": "crisis", "death": "death", "historical_shock": "crisis"}
QUESTION = {"migration_opportunity": "Will migration improve the family's finances?", "migration": "Will the move abroad pay off — and at what cost to family life?",
            "enter_university": "Can the household afford university, and will it change his prospects?", "business_start": "Does the business risk pay off?",
            "job_loss": "Will unemployment destroy the savings built so far?", "financial_distress": "Can the household get out of debt?",
            "marriage": "Can two incomes — or one — carry a new household?", "child_born": "Can the household absorb the cost of another child?",
            "retirement": "Will savings last without a modelled pension?", "purchase": "Will the mortgage become security or a burden?",
            "major_condition_onset": "How will illness change work and money?", "failed_migration": "What does a failed attempt cost?",
            "return_migration": "What does coming home mean after years away?"}
EMOTION = {"migration": ["uncertainty", "isolation"], "failed_migration": ["regret"], "marriage": ["joy"], "child_born": ["joy", "responsibility"],
           "job_loss": ["stress", "uncertainty"], "financial_distress": ["stress"], "deprivation": ["stress"], "divorce": ["grief"], "widowhood": ["grief"],
           "promotion": ["pride"], "business_success": ["pride", "relief"], "business_failure": ["regret", "stress"], "retirement": ["relief", "uncertainty"],
           "death": ["grief"], "enter_university": ["pride"], "first_job": ["pride", "responsibility"], "purchase": ["pride", "responsibility"],
           "return_migration": ["relief"], "major_condition_onset": ["uncertainty"], "inheritance": ["grief", "relief"], "major_asset_loss": ["stress"]}


def money(cur: str, v) -> str:
    return f"{cur} {Decimal(str(v)).quantize(Decimal('1')):,}"


def cname(c: str) -> str:
    return COUNTRY_NAME.get(c, c)


def _chapter(e: dict, ret_age: int | None) -> str:
    c = TYPE_CHAPTER.get(e["eventType"])
    if c == "career" and e["age"] >= 50:
        return "later"
    if c == "crisis" or c is None:
        if c is None:
            return "childhood" if e["age"] < 12 else "career" if e["age"] < 40 else "middle" if e["age"] < 55 else "final"
    if c == "middle" and e["age"] < 40:
        return "career"
    if c == "final" and ret_age is None and e["age"] < 60:
        return "middle"
    return c


def _sentence(e: dict, st_before: dict | None, st_after: dict | None, cur: str) -> str:
    t, y, a = e["eventType"], e["year"], e["age"]
    p = e.get("probability")
    odds = f" (modeled probability {p * 100:.1f}%)" if p is not None else ""
    sa = (st_after or {}).get("economics") or {}
    country = cname((st_after or {}).get("country") or "")
    T = {
        "birth": f"The simulated life begins in {y}.",
        "enroll_primary": f"At {a}, he is modeled as starting primary school{odds}.",
        "enter_university": f"In {y}, at {a}, the simulation sends him to university{odds}.",
        "enter_vocational": f"At {a}, the simulated path turns to vocational training{odds}.",
        "dropout": f"At {a}, the modeled schooling ends early{odds}.",
        "first_job": f"In {y}, at {a}, the simulation has him find a first job in {country}{odds}, earning a simulated {money(cur, sa.get('income', {}).get('wages', 0))} that year.",
        "meet_partner": f"At {a}, the simulated life gains a partner{odds}.",
        "marriage": f"In {y} he marries in the simulation{odds}.",
        "separation": f"In {y} the modeled marriage breaks down{odds}.",
        "divorce": f"By {y} the simulated separation ends in divorce.",
        "widowhood": f"In {y}, at {a}, the simulation records the death of his partner.",
        "child_born": f"In {y} a child is born in the simulated household{odds}.",
        "migration_opportunity": f"In {y}, at {a}, a modeled migration opportunity appears{odds}.",
        "migration": f"In {y} he moves to {country} in this simulation.",
        "failed_migration": f"The simulated attempt to emigrate in {y} falls through{odds}.",
        "return_migration": f"In {y} the simulation brings him back to {country}{odds}.",
        "promotion": f"At {a} the modeled career advances with a promotion{odds}.",
        "job_loss": f"In {y}, at {a}, the simulated job is lost{odds}.",
        "business_start": f"In {y} he starts a business in the simulation{odds}.",
        "business_success": f"In {y} the simulated business takes off{odds}.",
        "business_failure": f"In {y} the simulated business fails{odds}.",
        "financial_distress": f"By {y} the modeled household is in financial distress.",
        "deprivation": f"In {y} the simulated household runs out of credit and some needs go unmet.",
        "forced_sale": f"In {y} the simulated household is forced to sell its home.",
        "purchase": f"In {y}, at {a}, the simulation has the household buy a home{odds}.",
        "retirement": f"At {a}, in {y}, he retires in the simulation{odds}.",
        "return_to_work": f"At {a} the simulated retiree returns to part-time work.",
        "major_condition_onset": f"At {a} the simulation records a major health condition{odds}.",
        "terminal_illness": f"At {a} the simulated illness becomes terminal.",
        "disability": f"At {a} the simulated health shock leaves him unable to work.",
        "inheritance": f"In {y} a modeled inheritance arrives{odds}.",
        "investment_windfall": f"In {y} the simulation grants a rare windfall{odds}.",
        "career_breakthrough": f"In {y} a rare modeled career breakthrough lifts his pay{odds}.",
        "major_asset_loss": f"In {y} the simulated household suffers a major asset loss{odds}.",
        "death": f"The simulated life ends in {y}, at age {a}, drawn from an annual mortality hazard{odds} — not from life expectancy.",
        "historical_shock": f"In {y} a verified historical event shapes the modeled economy.",
    }
    return T.get(t, f"In {y}, at {a}, the simulation records: {t.replace('_', ' ')}{odds}.")


def build(payload: dict, run: dict, states: list[dict], events: list[dict]) -> dict:
    ch = payload["character"]
    b = ch["birthYear"]
    by_year = {s["year"]: s for s in states}
    ret_age = run["outcome"].get("retirementAge")
    claims: list[dict] = []
    beats: list[dict] = []

    def claim(text, typ, refs, year=None, nums=(), chapter=None):
        c = {"id": f"C{len(claims) + 1}", "text": text, "type": typ, "refs": list(refs), "year": year, "age": None if year is None else year - b,
             "numbers": list(nums), "chapter": chapter}
        claims.append(c)
        return c

    major = [e for e in events if e["occurred"] and (e["importance"] >= 3 or e["eventType"] in ("historical_shock", "promotion"))]
    # birth context
    chap_claims: dict[str, list[dict]] = {}
    c0 = claim(f"{ch.get('name') or 'The character'} is defined in Character DNA as born in {b} in {ch.get('region') or ''}, {ch.get('countryName') or cname(ch['country'])}"
               f" — a fictional composite, not a real person (character assumption).", "ASSUMPTION", ["character-dna"], b, [str(b)], "birth")
    chap_claims.setdefault("birth", []).append(c0)
    ser = payload["evidence"]["series"]
    for metric, label, unit in (("IMR", "infant mortality", "per 1,000 live births"), ("LExMale", "male life expectancy at birth", "years")):
        s = ser.get(f"{metric}|{ch['country']}|{'MALE' if metric == 'LExMale' else ''}|0") or ser.get(f"{metric}|{ch['country']}||") or ser.get(f"{metric}|{ch['country']}|MALE|")
        if s:
            yr = min(s, key=lambda y: abs(int(y) - b))
            if abs(int(yr) - b) <= 2:
                v, oid, _ = s[yr]
                txt = f"In {yr}, {label} in {cname(ch['country'])} was {Decimal(v).quantize(Decimal('0.1'))} {unit} (UN World Population Prospects)."
                chap_claims["birth"].append(claim(txt, "FACTUAL_CONTEXT", [oid], int(yr), [str(Decimal(v).quantize(Decimal('0.1')))], "birth"))
    for ev in payload["evidence"]["events"]:
        if ev["verification"] != "verified":
            continue
        y0 = int(str(ev.get("start") or "0")[:4] or 0)
        if b <= y0 <= (run["outcome"].get("deathYear") or b + 100) and (ch["country"] in ev["geography"] or "WORLD" in ev["geography"] or any(s["country"] in ev["geography"] for s in states if s["year"] == y0)):
            age = y0 - b
            chap = "childhood" if age < 12 else "career" if age < 40 else "middle" if age < 55 else "final"
            chap_claims.setdefault(chap, []).append(claim(f"{y0}: {ev['name']} (verified historical context).", "FACTUAL_CONTEXT", [ev["id"]], y0, [str(y0)], chap))
    for e in major:
        if e["eventType"] == "historical_shock":
            continue
        cur = (by_year.get(e["year"]) or {}).get("currency") or ""
        before = by_year.get(e["year"] - 1)
        after = by_year.get(e["year"])
        chap = _chapter(e, ret_age)
        txt = _sentence(e, before, after, cur)
        nums = re.findall(r"\d[\d,]*(?:\.\d+)?", txt)
        typ = "ASSUMPTION" if e["probabilityClass"] == "ASSUMPTION_BASED" and e["probability"] is None else "SIMULATED_EVENT"
        cl = claim(txt, typ, [e["id"]] + e.get("evidenceIds", [])[:3] + e.get("assumptionIds", []), e["year"], nums, chap)
        chap_claims.setdefault(chap, []).append(cl)
        later = by_year.get(e["year"] + 5) or (states[-1] if states else None)
        econ_ctx = None
        if after and after.get("economics"):
            ec = after["economics"]
            econ_ctx = {"currency": ec["currency"], "income": ec["totalIncome"], "netWorth": ec["netWorth"].get(ec["currency"])}
            if e["eventType"] in ("migration", "job_loss", "business_start", "purchase", "retirement", "child_born", "marriage", "failed_migration", "financial_distress") and before and before.get("economics"):
                nb = before["economics"]["netWorth"].get(before["currency"], "0")
                na = later["economics"]["netWorth"].get(later["currency"], "0") if later else None
                if na is not None:
                    t2 = (f"Five modeled years later ({later['year']}), simulated net worth stood at {money(later['currency'], na)}, against "
                          f"{money(before['currency'], nb)} the year before (DERIVED from the simulated ledger).")
                    chap_claims[chap].append(claim(t2, "DERIVED_DATA", [e["id"], f"ledger:{later['year']}", f"ledger:{before['year']}"], later["year"],
                                                   re.findall(r"\d[\d,]*", t2), chap))
        emo = EMOTION.get(e["eventType"], [])
        if emo and e["importance"] >= 3:
            chap_claims[chap].append(claim(f"Narrative interpretation: a moment of {' and '.join(emo)}.", "NARRATIVE_INTERPRETATION", [e["id"]], e["year"], [], chap))
        beats.append({"id": f"B{len(beats) + 1}", "year": e["year"], "age": e["age"], "chapter": chap, "chapterTitle": TITLE[chap], "events": [e["id"]],
                      "setup": None if not before else f"{before['year']}: {before['employment']} in {cname(before['country'])}, household of "
                                                         f"{before['economics'].get('householdSize', 1)}, simulated net worth {money(before['currency'], before['netWorth'])}.",
                      "tension": QUESTION.get(e["eventType"]), "decision": None if e["probability"] is None else
                      f"Modeled probability {e['probability'] * 100:.1f}% [{e['probabilityClass']}], draw {e['randomDraw']}",
                      "consequence": txt, "payoff": None if not later else f"By {later['year']}: {later['employment']}, net worth {money(later['currency'], later['netWorth'])}",
                      "importance": e["importance"], "economicContext": econ_ctx, "emotionalInterpretation": {"labels": emo, "type": "NARRATIVE_INTERPRETATION"},
                      "sources": {"eventId": e["id"], "evidenceIds": e.get("evidenceIds", []), "assumptionIds": e.get("assumptionIds", []), "priorIds": e.get("priorIds", [])},
                      "claimIds": [cl["id"]]})
    # receipt chapter
    last = states[-1]
    chap_claims.setdefault("receipt", []).append(claim(
        f"Over the simulated life he earned " + ", ".join(money(c, v) for c, v in run["outcome"]["lifetimeEarnings"].items()) + " in nominal wages, and left a simulated estate of "
        + ", ".join(money(c, v) for c, v in run["outcome"]["netWorthAtDeath"].items()) + " (DERIVED from the simulated ledger).",
        "DERIVED_DATA", [f"ledger:{last['year']}", run["id"]], last["year"], [], "receipt"))
    for c in claims:
        if not c["numbers"]:
            c["numbers"] = re.findall(r"\d[\d,]*(?:\.\d+)?", c["text"])
    order = [k for k, _ in CHAPTERS]
    chapters = []
    for k in order:
        cl = chap_claims.get(k) or []
        if not cl or (k not in ("birth", "receipt") and not any(x["type"] in ("SIMULATED_EVENT", "ASSUMPTION", "FACTUAL_CONTEXT") for x in cl)):
            continue
        yrs = [x["year"] for x in cl if x["year"] is not None]
        chapters.append({"key": k, "number": len(chapters) + 1, "title": TITLE[k], "yearStart": min(yrs) if yrs else None, "yearEnd": max(yrs) if yrs else None,
                         "claimIds": [x["id"] for x in cl], "beatIds": [bt["id"] for bt in beats if bt["chapter"] == k],
                         "questions": sorted({bt["tension"] for bt in beats if bt["chapter"] == k and bt["tension"]}),
                         "draft": " ".join(x["text"] for x in cl)})
    return {"label": DRAFT_LABEL, "runId": run["id"], "chapters": chapters, "beats": beats, "claims": claims,
            "claimTypes": list(CLAIM_TYPES), "engagement": "Questions arise only from modeled turning points; no artificial cliffhangers."}


def story_audit(story: dict, payload: dict, states: list[dict], events: list[dict]) -> list[dict]:
    out = []
    b = payload["character"]["birthYear"]
    ev_ids = {e["id"]: e for e in events}
    by_year = {s["year"]: s for s in states}
    last_year = states[-1]["year"] if states else None
    allowed = allowed_numbers(story, states)
    for c in story["claims"]:
        if c["type"] not in CLAIM_TYPES:
            out.append({"ruleId": "claim-provenance", "severity": "error", "message": f"{c['id']}: unknown claim type"})
        if c["type"] != "NARRATIVE_INTERPRETATION" and not c["refs"]:
            out.append({"ruleId": "claim-provenance", "severity": "error", "message": f"{c['id']}: no provenance refs"})
        low = c["text"].lower()
        if c["type"] == "SIMULATED_EVENT" and not re.search(r"simulat|model", low):
            out.append({"ruleId": "simulation-as-fact", "severity": "error", "message": f"{c['id']}: simulated event worded as historical fact"})
        if c["type"] == "ASSUMPTION" and "assum" not in low:
            out.append({"ruleId": "assumption-as-fact", "severity": "error", "message": f"{c['id']}: assumption not labelled as such"})
        if c["year"] is not None and c["age"] != c["year"] - b:
            out.append({"ruleId": "age-mismatch", "severity": "error", "message": f"{c['id']}: age mismatch"})
        if c["year"] is not None and last_year is not None and c["year"] > last_year and c["type"] != "FACTUAL_CONTEXT":
            out.append({"ruleId": "timeline-contradiction", "severity": "error", "message": f"{c['id']}: claim after the simulated death"})
        for r in c["refs"]:
            if r.startswith("RUN-") and ":" in r:
                if r not in ev_ids or not ev_ids[r]["occurred"]:
                    out.append({"ruleId": "contradicts-canonical", "severity": "error", "message": f"{c['id']}: refers to {r}, not an occurred event of the canonical run"})
                elif ev_ids[r]["year"] != c["year"] and c["type"] == "SIMULATED_EVENT":
                    out.append({"ruleId": "wrong-year", "severity": "error", "message": f"{c['id']}: year differs from event {r}"})
        for n in c["numbers"]:
            if n.replace(",", "") not in allowed:
                out.append({"ruleId": "unsupported-number", "severity": "warning", "message": f"{c['id']}: number {n} not found in run data"})
        if c["type"] == "SIMULATED_EVENT" and c["year"] in by_year:
            m_ = re.search(r"moves to ([A-Za-z ]+?) in this simulation", c["text"])
            if m_ and cname(by_year[c["year"]]["country"]) != m_.group(1).strip():
                out.append({"ruleId": "wrong-country", "severity": "error", "message": f"{c['id']}: country does not match the simulated state"})
    return out


def allowed_numbers(story: dict, states: list[dict]) -> set[str]:
    s: set[str] = set()
    for c in story["claims"]:
        s |= {n.replace(",", "") for n in c["numbers"]}
    for st in states:
        s |= {str(st["year"]), str(st["age"])}
        for v in list((st["economics"].get("netWorth") or {}).values()) + [st["economics"].get("totalIncome"), st["income"]]:
            if v is not None:
                s.add(str(Decimal(str(v)).quantize(Decimal("1"))))
    return s


# ----------------------------------------------------------------- production
VISUAL = {"migration": "Departure gate / arrivals hall; luggage, documents; establishing shot of destination skyline in {year}",
          "first_job": "Workplace interior typical of {country} in {year}; hands at work", "marriage": "Wedding details; family gathering",
          "child_born": "Hospital corridor / home with newborn; warm light", "job_loss": "Empty desk, letter, quiet room",
          "financial_distress": "Bills on a table, calculator, night", "retirement": "Last day at work; farewell", "death": "Empty chair; archival photographs",
          "purchase": "Keys handed over; new apartment", "business_start": "Shopfront opening", "birth": "Archival street scene, {country} {year}"}


def production(story: dict, run: dict, states: list[dict], timeline_ids: dict[str, str]) -> dict:
    by_year = {s["year"]: s for s in states}
    claims = {c["id"]: c for c in story["claims"]}
    scenes = []
    for ch in story["chapters"]:
        cls = [claims[i] for i in ch["claimIds"]]
        groups: dict[int, list] = {}
        for c in cls:
            groups.setdefault(c["year"] if c["year"] is not None else -1, []).append(c)
        for yr, cl in sorted(groups.items()):
            st = by_year.get(yr) or {}
            narration = " ".join(c["text"] for c in cl)
            words = len(narration.split())
            ev_ids = [r for c in cl for r in c["refs"] if r.startswith("RUN-")]
            etype = next((r.split(":")[0] for r in ev_ids), None)
            kind = next((b["events"] for b in story["beats"] if b["year"] == yr), None)
            vk = next((k for k in VISUAL if any(k in c["text"].lower().replace(" ", "_") for c in cl)), "birth" if ch["key"] == "birth" else None)
            scenes.append({"sceneNumber": len(scenes) + 1, "chapter": ch["title"], "year": None if yr == -1 else yr, "age": None if yr == -1 else cl[0]["age"],
                           "location": cname(st.get("country", "")) if st else "", "description": f"{ch['title']} — {yr}" if yr != -1 else ch["title"],
                           "narration": narration, "visualConcept": (VISUAL.get(vk) or "Archival-style b-roll matching {country}, {year}").format(year=yr, country=cname(st.get("country", "")) if st else ""),
                           "timelineEventIds": [timeline_ids[e] for e in ev_ids if e in timeline_ids], "factIds": [r for c in cl for r in c["refs"] if r.startswith("LO:") or r.startswith("EV-")],
                           "sourceIds": sorted({r for c in cl for r in c["refs"]}), "claimIds": [c["id"] for c in cl],
                           "estimatedDuration": round(words / 150 * 60, 1), "labels": sorted({c["type"] for c in cl})})
            _ = (etype, kind)
    script = render_script(story, scenes)
    return {"summary": f"A simulated life ({run['outcome'].get('deathAge')} years) generated by LifeSpan run {run['id']} — {len(story['chapters'])} chapters, {len(scenes)} scenes.",
            "outline": [{"number": c["number"], "title": c["title"], "years": [c["yearStart"], c["yearEnd"]], "questions": c["questions"]} for c in story["chapters"]],
            "scenes": scenes, "script": script, "scriptEdited": False, "visualNotes": [s["visualConcept"] for s in scenes],
            "narrationNotes": ["Read SIMULATED events with modal phrasing ('in this simulation', 'modeled').", "Factual context lines cite their source on screen.",
                               "Narrative interpretations are framed as interpretation, never as measurement."], "label": DRAFT_LABEL}


def render_script(story: dict, scenes: list[dict]) -> str:
    out = [f"[{DRAFT_LABEL}]", ""]
    cur = None
    for s in scenes:
        if s["chapter"] != cur:
            cur = s["chapter"]
            out += [f"## {cur}", ""]
        out += [f"[Scene {s['sceneNumber']} · {s['year'] or ''} · {s['location']}]", s["narration"], ""]
    return "\n".join(out)


def script_check(script: str, story: dict, states: list[dict]) -> dict:
    words = len(re.findall(r"\b\w+\b", script))
    allowed = allowed_numbers(story, states)
    warnings = []
    for n in sorted(set(re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", script))):
        if n.replace(",", "") not in allowed and not re.fullmatch(r"\d{1,2}", n):
            warnings.append({"ruleId": "unsupported-number", "message": f"Number {n} is not found in the canonical run or its cited evidence"})
    if "SIMULATED" not in script and "simulat" not in script.lower():
        warnings.append({"ruleId": "simulation-label", "message": "Script no longer labels the life as simulated"})
    for m_ in re.finditer(r"(?im)^(?!\[).*\b(in fact|historically,|records show)\b.*$", script):
        warnings.append({"ruleId": "simulation-as-fact", "message": f"Factual phrasing on a simulated line: {m_.group(0)[:80]}"})
    return {"wordCount": words, "estimatedRuntimeSeconds": round(words / 150 * 60), "warnings": warnings,
            "chapters": re.findall(r"(?m)^## (.+)$", script)}


# ----------------------------------------------------------------- Life Receipt 2.0 + source appendix
def receipt(payload: dict, run: dict, states: list[dict], events: list[dict]) -> dict:
    o = run["outcome"]
    occ = [e for e in events if e["occurred"]]
    typ = lambda *ts: [e for e in occ if e["eventType"] in ts]  # noqa: E731
    first_job = next(iter(typ("first_job")), None)
    infl = {}
    for cur in o["lifetimeEarnings"]:
        yrs = [(s["year"], Decimal(s["income"])) for s in states if s["currency"] == cur and Decimal(s["income"]) > 0]
        country = next((s["country"] for s in states if s["currency"] == cur), None)
        cpi = payload["evidence"].get("cpi", {}).get(country, {})
        last_y = max((int(y) for y in cpi), default=None)
        if yrs and last_y and all(str(y) in cpi for y, _ in yrs):
            base = Decimal(cpi[str(last_y)][0])
            infl[cur] = {"value": str(sum((w * base / Decimal(cpi[str(y)][0]) for y, w in yrs), Decimal(0)).quantize(Decimal("0.01"))),
                         "priceYear": last_y, "status": "DERIVED (World Bank CPI)"}
        else:
            missing = sum(1 for y, _ in yrs if str(y) not in cpi)
            infl[cur] = {"value": None, "status": f"Not supported — CPI missing for {missing} of {len(yrs)} earning years"}
    peak_debt = {}
    for s in states:
        for c, a in (s["state"].get("acc") or {}).items():
            d = Decimal(a.get("debt", "0")) + Decimal(a.get("mortgage", "0"))
            if d > Decimal(peak_debt.get(c, "0")):
                peak_debt[c] = str(d)
    used_ev = sorted({i for e in events for i in e.get("evidenceIds") or []} | {i for s in states for i in ((s["economics"].get("wageProvenance") or {}).get("evidenceIds") or [])})
    used_asm = sorted({i for e in events for i in e.get("assumptionIds") or []} | {i for s in states for i in s["economics"].get("assumptionIds") or []})
    used_pri = sorted({i for e in events for i in e.get("priorIds") or []} | {i for s in states for i in s["economics"].get("priorIds") or []})
    last = states[-1]
    return {"label": "LIFE RECEIPT 2.0 — every value below is SIMULATED unless marked DERIVED/EVIDENCE",
            "birthYear": payload["character"]["birthYear"], "deathYear": o.get("deathYear"), "ageAtDeath": o.get("deathAge"),
            "countriesLivedIn": [cname(c) for c in o.get("countries", [])], "education": o.get("education"),
            "career": {"firstJob": first_job and {"year": first_job["year"], "age": first_job["age"]}, "occupation": last["state"]["emp"].get("occupation"),
                       "promotions": len(typ("promotion")), "jobLosses": len(typ("job_loss")), "businessAttempt": o.get("businessAttempt"), "businessSuccess": o.get("businessSuccess")},
            "relationships": [f"{e['year']} {e['eventType'].replace('_', ' ')}" for e in typ("meet_partner", "marriage", "separation", "divorce", "widowhood")],
            "children": o.get("children"), "yearsEmployed": o.get("yearsEmployed"), "yearsUnemployed": o.get("yearsUnemployed"), "yearsRetired": o.get("yearsRetired"),
            "lifetimeNominalEarnings": o.get("lifetimeEarnings"), "inflationAdjustedEarnings": infl, "lifetimeSpending": o.get("lifetimeSpending"),
            "peakIncome": o.get("peakIncome"), "peakNetWorth": o.get("peakNetWorth"), "netWorthAtDeath": o.get("netWorthAtDeath"),
            "housing": {"final": last["state"].get("housing"), "everOwned": o.get("homeOwner")}, "peakDebt": peak_debt,
            "migration": [f"{h['year']}: {cname(h['from'])} → {cname(h['to'])}" for h in last["state"]["mig"].get("history", [])],
            "turningPoints": [f"{e['year']} (age {e['age']}): {e['eventType'].replace('_', ' ')}" for e in occ if e["importance"] >= 3 and e["eventType"] not in ("birth", "estate")][:15],
            "majorLosses": [f"{e['year']}: {e['eventType'].replace('_', ' ')}" for e in typ("job_loss", "business_failure", "major_asset_loss", "financial_distress", "divorce", "widowhood", "forced_sale", "failed_migration")],
            "majorAchievements": [f"{e['year']}: {e['eventType'].replace('_', ' ')}" for e in typ("enter_university", "complete_tertiary", "business_success", "purchase", "career_breakthrough", "migration")],
            "provenance": {"runId": run["id"], "simulationSeed": run["seed"], "engineVersion": run["engineVersion"], "datasetSnapshot": payload["snapshot"],
                           "verifiedEvidenceCount": len(used_ev), "assumptionCount": len(used_asm), "provisionalPriorCount": len(used_pri),
                           "evidenceIds": used_ev, "assumptionIds": used_asm, "priorIds": used_pri}}


def source_appendix(payload: dict, run: dict, states: list[dict], events: list[dict], facts: list[dict], sources: list[dict]) -> dict:
    rc = receipt(payload, run, states, events)["provenance"]
    derived = sorted({(s["economics"].get("wageProvenance") or {}).get("method") for s in states if s["economics"].get("wageProvenance")} - {None})
    pri = payload["priors"]
    by_id = {p["id"]: p for p in pri.values()}
    return {"Verified Sources": [{"id": s["id"], "title": s.get("title"), "organization": s.get("organization"), "url": s.get("url")} for s in sources],
            "External Observations": [{"id": i} for i in rc["evidenceIds"]],
            "Derived Calculations": [{"method": d} for d in derived] + [{"method": "Mortality single-age hazards (Gompertz level from UN WPP Q15–60)"}],
            "Assumptions": [{"id": a["id"], "claim": a["claim"], "value": a.get("value"), "unit": a.get("unit")} for a in payload["assumptions"] if a["id"] in rc["assumptionIds"]],
            "Provisional Priors": [{"id": i, "name": by_id.get(i, {}).get("name"), "label": "Provisional model prior — not externally validated"} for i in rc["priorIds"]],
            "Simulated Outcomes": [{"runId": run["id"], "events": sum(1 for e in events if e["occurred"]), "years": len(states), "label": "SIMULATED"}],
            "Prototype Inputs": [{"note": "Prototype economic-ledger rows and prototype facts are excluded from snapshots and never feed the simulation."}],
            "Facts in snapshot": [{"id": f.get("id"), "metric": f.get("metric"), "value": f.get("value"), "unit": f.get("unit")} for f in facts]}
