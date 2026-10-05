import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { Check, Flag, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, Field, PageHeader } from "@/components/lifespan/primitives";
import { ApiError, lifespanApi } from "@/services/lifespanApi";
import { LIFE_STAGES, type BaselineInput, type CandidateResult, type EconomicBaseline, type EconomicProfile, type EconomicProfileInput, type EvidenceGap, type Household, type LifeStageKey, type MatchCandidate, type Readiness } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";
import { fmtWage } from "./labor";

export const Route = createFileRoute("/evidence")({
  head: pageHead("Employment Evidence", "Match a character's life stages to published wage statistics and record human-reviewed economic baselines."),
  component: Evidence,
});

const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed.");
const blank = (birth: number, country: string): EconomicProfileInput => ({
  lifeStage: "first-employment", targetYear: birth + 20, yearStart: birth + 20, yearEnd: birth + 23, country, region: "", urbanRural: "", educationLevel: "",
  occupation: "", occupationCode: "", occupationClassification: "ISCO-08", industry: "", industryCode: "", employmentStatus: "EMPLOYEE", formalInformal: "",
  yearsExperience: null, age: null, sex: "", citizenship: "", migrantStatus: "", employmentSector: "", notes: "",
});
const range = (b: EconomicBaseline) => (b.point ? fmtWage(b.point) : `${fmtWage(b.low)} – ${fmtWage(b.high)}`);
const confTone = (c: string) => (c === "HIGH" ? "border-pass text-pass" : c === "MEDIUM" ? "border-fact text-fact" : c === "LOW" ? "border-warn text-warn" : "border-fail text-fail");

function Evidence() {
  const { active, mode, reload } = useLifespan();
  const api = lifespanApi.labor;
  const [profiles, setProfiles] = useState<EconomicProfile[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [cands, setCands] = useState<CandidateResult | null>(null);
  const [baselines, setBaselines] = useState<EconomicBaseline[]>([]);
  const [gaps, setGaps] = useState<EvidenceGap[]>([]);
  const [ready, setReady] = useState<Readiness | null>(null);
  const [hh, setHh] = useState<Household[]>([]);
  const [draft, setDraft] = useState<EconomicProfileInput | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [accept, setAccept] = useState<{ c: MatchCandidate; type: BaselineInput["baselineType"] } | null>(null);
  const [assume, setAssume] = useState<{ low: string; high: string; point: string; currency: string; payPeriod: string; reasoning: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const eid = active?.id;
  const ch = active?.character;

  const refresh = useCallback(async () => {
    if (!eid) return;
    try {
      const [p, b, g, r, h] = await Promise.all([api.profiles(eid), api.baselines(eid), api.gaps(eid), api.readiness(eid), api.households(eid)]);
      setProfiles(p);
      setBaselines(b);
      setGaps(g);
      setReady(r);
      setHh(h);
      setSel((s) => s ?? p[0]?.id ?? null);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [api, eid]);
  useEffect(() => {
    if (mode === "backend") void refresh();
  }, [mode, refresh]);
  useEffect(() => {
    if (!sel) return setCands(null);
    api.candidates(sel).then(setCands).catch((e) => setError(errMsg(e)));
  }, [api, sel, baselines]);

  const run = async (fn: () => Promise<unknown>, msg?: string) => {
    setError(null);
    setNotice(null);
    try {
      await fn();
      if (msg) setNotice(msg);
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  if (mode !== "backend")
    return (<><PageHeader eyebrow="Evidence" title="Employment Evidence" /><div className="panel p-6 text-sm text-muted-foreground">Requires the LifeSpan backend (<code className="data">./scripts/start-local.sh</code>).</div></>);
  if (!active || !ch || !eid) return <EmptyEpisode />;

  const saveProfile = () => draft && run(async () => {
    const p = editing ? await api.updateProfile(editing, draft) : await api.createProfile(eid, draft);
    setSel(p.id);
    setDraft(null);
    setEditing(null);
  }, "Profile saved. It describes what evidence to search for — it is not a wage claim.");
  const prof = profiles.find((p) => p.id === sel);

  const createBaseline = (b: BaselineInput) => run(async () => {
    await api.createBaseline(eid, b);
    setAccept(null);
    setAssume(null);
    await reload();
  }, "Baseline recorded as a draft. Review it, then approve.");

  return (
    <>
      <PageHeader eyebrow="Evidence · Labour" title="Employment Evidence" description={`${active.title}. Deterministic matching ranks published statistics by how well their population matches each life stage. Nothing is chosen automatically.`} />
      {error && <div className="mb-4 rounded-sm border border-fail/50 bg-fail/5 p-2 text-sm text-fail">{error}</div>}
      {notice && <div className="mb-4 rounded-sm border border-pass/40 bg-pass/5 p-2 text-sm text-pass">{notice}</div>}

      {ready && (
        <section className="panel mb-6 p-4">
          <div className="flex items-baseline gap-3"><div className="eyebrow">Economic data readiness</div><div className="data text-2xl">{ready.overall}%</div><div className="text-xs text-muted-foreground">{ready.note}</div></div>
          <div className="mt-3 grid grid-cols-6 gap-2 text-xs">
            {ready.stages.map((s) => (
              <div key={s.stage} className="rounded-sm border border-border p-2">
                <div className="font-medium">{s.label}</div>
                <div className={cn("mt-1 chip", s.status === "READY" ? "border-pass text-pass" : s.status === "PARTIAL" ? "border-warn text-warn" : "border-fail text-fail")}>{s.status}</div>
                <div className="mt-1 text-muted-foreground">{s.reasons.join("; ")}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid grid-cols-[300px_1fr] gap-6">
        <section className="panel self-start">
          <div className="panel-header"><h3 className="text-base">Economic profiles</h3><button className="btn-ghost" onClick={() => { setEditing(null); setDraft(blank(ch.birthYear, "IND")); }}><Plus className="h-3.5 w-3.5" /> Add</button></div>
          <ul className="divide-y divide-border text-sm">
            {profiles.map((p) => (
              <li key={p.id} className={cn("cursor-pointer px-4 py-2", sel === p.id && "bg-accent")} onClick={() => setSel(p.id)}>
                <div className="font-medium">{p.lifeStageLabel} · {p.yearStart}–{p.yearEnd}</div>
                <div className="text-xs text-muted-foreground">{p.country} {p.region} · {p.occupation || "occupation not set"} {p.occupationCode && `(${p.occupationClassification} ${p.occupationCode})`}</div>
              </li>
            ))}
            {profiles.length === 0 && <li className="px-4 py-6 text-xs text-muted-foreground">No profiles yet. Add one per life stage (e.g. first job in Delhi, Dubai work).</li>}
          </ul>
        </section>

        <div>
          {draft && (
            <section className="panel mb-6 p-4">
              <div className="eyebrow mb-3">{editing ? "Edit" : "New"} economic profile — describes what evidence to search for</div>
              <div className="grid grid-cols-4 gap-3 text-sm">
                <Field label="Life stage"><select aria-label="Life stage" className="input" value={draft.lifeStage} onChange={(e) => setDraft({ ...draft, lifeStage: e.target.value as LifeStageKey })}>{LIFE_STAGES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</select></Field>
                <Field label="Target year"><input aria-label="Target year" type="number" className="input data" value={draft.targetYear} onChange={(e) => setDraft({ ...draft, targetYear: Number(e.target.value) })} /></Field>
                <Field label="From year"><input aria-label="Profile from" type="number" className="input data" value={draft.yearStart} onChange={(e) => setDraft({ ...draft, yearStart: Number(e.target.value) })} /></Field>
                <Field label="To year"><input aria-label="Profile to" type="number" className="input data" value={draft.yearEnd} onChange={(e) => setDraft({ ...draft, yearEnd: Number(e.target.value) })} /></Field>
                <Field label="Country (ISO3)"><input aria-label="Profile country" className="input data" value={draft.country} onChange={(e) => setDraft({ ...draft, country: e.target.value.toUpperCase() })} /></Field>
                <Field label="Region / city"><input aria-label="Profile region" className="input" value={draft.region} onChange={(e) => setDraft({ ...draft, region: e.target.value })} /></Field>
                <Field label="Urban / rural"><select aria-label="Urban rural" className="input" value={draft.urbanRural} onChange={(e) => setDraft({ ...draft, urbanRural: e.target.value as EconomicProfileInput["urbanRural"] })}><option value="">Not specified</option><option>URBAN</option><option>RURAL</option></select></Field>
                <Field label="Education (ILO aggregate)"><select aria-label="Education level" className="input" value={draft.educationLevel} onChange={(e) => setDraft({ ...draft, educationLevel: e.target.value as EconomicProfileInput["educationLevel"] })}><option value="">Not specified</option><option value="LTB">Less than basic</option><option value="BAS">Basic</option><option value="INT">Intermediate</option><option value="ADV">Advanced</option></select></Field>
                <Field label="Occupation"><input aria-label="Occupation" className="input" value={draft.occupation} onChange={(e) => setDraft({ ...draft, occupation: e.target.value })} /></Field>
                <Field label="ISCO major group (0–9)"><input aria-label="Occupation code" className="input data" value={draft.occupationCode} onChange={(e) => setDraft({ ...draft, occupationCode: e.target.value })} /></Field>
                <Field label="Classification"><select aria-label="Occupation classification" className="input" value={draft.occupationClassification} onChange={(e) => setDraft({ ...draft, occupationClassification: e.target.value as "ISCO-08" | "ISCO-88" })}><option>ISCO-08</option><option>ISCO-88</option></select></Field>
                <Field label="Employment status"><select aria-label="Employment status" className="input" value={draft.employmentStatus} onChange={(e) => setDraft({ ...draft, employmentStatus: e.target.value as EconomicProfileInput["employmentStatus"] })}><option value="">Not specified</option><option>EMPLOYEE</option><option>SELF_EMPLOYED</option><option>EMPLOYER</option><option>UNPAID</option></select></Field>
                <Field label="Formal / informal"><select aria-label="Formal informal" className="input" value={draft.formalInformal} onChange={(e) => setDraft({ ...draft, formalInformal: e.target.value as EconomicProfileInput["formalInformal"] })}><option value="">Not specified</option><option>FORMAL</option><option>INFORMAL</option></select></Field>
                <Field label="Sex"><select aria-label="Profile sex" className="input" value={draft.sex} onChange={(e) => setDraft({ ...draft, sex: e.target.value as EconomicProfileInput["sex"] })}><option value="">Not specified</option><option>MALE</option><option>FEMALE</option></select></Field>
                <Field label="Citizenship"><select aria-label="Citizenship" className="input" value={draft.citizenship} onChange={(e) => setDraft({ ...draft, citizenship: e.target.value as EconomicProfileInput["citizenship"] })}><option value="">Not specified</option><option>NATIONAL</option><option>NON_NATIONAL</option></select></Field>
                <Field label="Age"><input aria-label="Age" type="number" className="input data" value={draft.age ?? ""} onChange={(e) => setDraft({ ...draft, age: e.target.value ? Number(e.target.value) : null })} /></Field>
              </div>
              <div className="mt-3 flex gap-2"><button className="btn-primary" onClick={() => void saveProfile()}>Save profile</button><button className="btn-ghost" onClick={() => setDraft(null)}>Cancel</button></div>
            </section>
          )}

          {prof && cands && (
            <section className="panel mb-6">
              <div className="panel-header">
                <div>
                  <h3 className="text-base">Best evidence — {prof.lifeStageLabel}, target {prof.targetYear}</h3>
                  <div className="text-xs text-muted-foreground">{prof.country} {prof.region} · {prof.urbanRural || "area n/s"} · edu {prof.educationLevel || "n/s"} · {prof.occupation || "occupation n/s"} · {prof.employmentStatus || "status n/s"} · {prof.citizenship || "citizenship n/s"} · {cands.totalConsidered} statistics considered</div>
                </div>
                <div className="flex gap-1">
                  <button className="btn-ghost" onClick={() => api.candidates(prof.id).then(setCands)}><RefreshCw className="h-3.5 w-3.5" /> Search again</button>
                  <button className="btn-ghost" onClick={() => { const { id: _i, episodeId: _e, lifeStageLabel: _l, ...rest } = prof; setEditing(prof.id); setDraft(rest); }}>Edit</button>
                  <button className="btn-ghost" onClick={() => void run(() => api.deleteProfile(prof.id).then(() => setSel(null)))}><Trash2 className="h-3.5 w-3.5" /></button>
                  <button className="btn" onClick={() => setAssume({ low: "", high: "", point: "", currency: prof.country === "ARE" ? "AED" : prof.country === "IND" ? "INR" : "", payPeriod: "MONTHLY", reasoning: "" })}>Add assumption</button>
                </div>
              </div>
              <div className="border-b border-border px-4 py-2 text-[11px] text-muted-foreground">{cands.note}</div>
              {cands.candidates.length === 0 && <div className="p-6 text-sm text-muted-foreground">No wage evidence stored. Fetch from ILOSTAT or import official tables on Labor Data. INSUFFICIENT DATA is a valid result.</div>}
              <ol className="divide-y divide-border">
                {cands.candidates.slice(0, 10).map((c, i) => (
                  <li key={c.wage.id} className={cn("px-4 py-3 text-sm", c.review?.decision === "rejected" && "opacity-50")}>
                    <div className="flex items-start gap-3">
                      <div className="w-14 text-center"><div className="data text-lg">{c.score}</div><div className="text-[10px] text-muted-foreground">/100</div></div>
                      <div className="flex-1">
                        <div className="font-medium">{i + 1}. {c.wage.sourcePopulation}</div>
                        <div className="text-xs">
                          <span className="data">{fmtWage(c.wage.value)} {c.wage.currency}</span> · {c.wage.statisticType.toLowerCase()} {c.wage.payPeriod.toLowerCase()} · {c.wage.grossOrNet} · {c.wage.provider} {c.wage.surveyName && `· ${c.wage.surveyName}`}
                          {" "}· Source year <b>{c.sourceYear}</b> / target <b>{c.targetYear}</b> / difference <b className={cn(c.yearDistance > 3 && "text-warn")}>{c.yearDistance} yr</b>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {c.breakdown.map((b) => <span key={b.dimension} title={b.note} className={cn("chip text-[10px]", b.points === b.max ? "border-pass text-pass" : b.points > 0 ? "border-warn text-warn" : "border-border text-muted-foreground")}>{b.dimension} {b.points}/{b.max}: {b.note}</span>)}
                        </div>
                        {c.review && <div className="mt-1 text-xs text-warn">{c.review.decision}{c.review.note && `: ${c.review.note}`}</div>}
                      </div>
                      <div className="flex flex-col gap-1">
                        <button className="btn text-xs" disabled={!c.countryMatch} onClick={() => setAccept({ c, type: c.yearDistance === 0 ? "FACT_SUPPORTED" : "DERIVED" })}><Check className="h-3 w-3" /> Accept as baseline</button>
                        <button className="btn-ghost text-xs" onClick={() => void run(() => api.review(prof.id, c.wage.id, c.review?.decision === "rejected" ? "clear" : "rejected").then(() => api.candidates(prof.id).then(setCands)))}><X className="h-3 w-3" /> {c.review?.decision === "rejected" ? "Undo reject" : "Reject"}</button>
                        <button className="btn-ghost text-xs" onClick={() => { const note = window.prompt("Describe the mismatch") ?? ""; void run(() => api.review(prof.id, c.wage.id, "flagged", note).then(() => api.candidates(prof.id).then(setCands))); }}><Flag className="h-3 w-3" /> Flag mismatch</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
              {cands.distributions.length > 0 && (
                <div className="border-t border-border px-4 py-3 text-xs">
                  <div className="eyebrow mb-1">Wage-group distributions for {prof.country}</div>
                  {cands.distributions.map((d) => <div key={d.id}>{d.metric} {d.year} ({d.yearDistance} yr from target) · {Object.values(d.dimensions).join(" · ")} · {d.bins.length} wage groups — interval evidence, not an exact salary</div>)}
                </div>
              )}
            </section>
          )}

          {accept && prof && (
            <section className="panel mb-6 border-primary p-4 text-sm">
              <div className="eyebrow mb-2">Accept evidence as baseline</div>
              <div>Evidence: {accept.c.wage.sourcePopulation} — <span className="data">{accept.c.wage.value} {accept.c.wage.currency}</span> ({accept.c.wage.statisticType.toLowerCase()}, {accept.c.wage.payPeriod.toLowerCase()}, {accept.c.wage.grossOrNet})</div>
              <div className="mt-2 flex gap-4">
                <label className="flex items-center gap-1.5"><input type="radio" checked={accept.type === "FACT_SUPPORTED"} disabled={accept.c.yearDistance !== 0} onChange={() => setAccept({ ...accept, type: "FACT_SUPPORTED" })} /> FACT_SUPPORTED (same year only)</label>
                <label className="flex items-center gap-1.5"><input type="radio" checked={accept.type === "DERIVED"} onChange={() => setAccept({ ...accept, type: "DERIVED" })} /> DERIVED — CPI-adjust {accept.c.sourceYear} → {prof.targetYear} (World Bank CPI must be stored)</label>
              </div>
              {accept.c.yearDistance > 5 && <div className="mt-2 text-xs text-warn">Evidence is {accept.c.yearDistance} years away. CPI adjustment gives a derived estimate, not a historical fact, and confidence will be LOW at best.</div>}
              <div className="mt-3 flex gap-2">
                <button className="btn-primary" onClick={() => void createBaseline({ profileId: prof.id, lifeStage: prof.lifeStage, yearStart: prof.yearStart, yearEnd: prof.yearEnd, baselineType: accept.type, wageObservationIds: [accept.c.wage.id], adjustToYear: accept.type === "DERIVED" ? prof.targetYear : null, occupation: prof.occupation })}>Create baseline</button>
                <button className="btn-ghost" onClick={() => setAccept(null)}>Cancel</button>
              </div>
            </section>
          )}

          {assume && prof && (
            <section className="panel mb-6 border-warn p-4 text-sm">
              <div className="eyebrow mb-2">Record an explicit ASSUMPTION (character-specific, not a source statistic)</div>
              <div className="grid grid-cols-5 gap-3">
                <Field label="Low"><input aria-label="Assumption low" className="input data" value={assume.low} onChange={(e) => setAssume({ ...assume, low: e.target.value })} /></Field>
                <Field label="High"><input aria-label="Assumption high" className="input data" value={assume.high} onChange={(e) => setAssume({ ...assume, high: e.target.value })} /></Field>
                <Field label="or point"><input aria-label="Assumption point" className="input data" value={assume.point} onChange={(e) => setAssume({ ...assume, point: e.target.value })} /></Field>
                <Field label="Currency"><input aria-label="Assumption currency" className="input data" value={assume.currency} onChange={(e) => setAssume({ ...assume, currency: e.target.value.toUpperCase() })} /></Field>
                <Field label="Pay period"><select aria-label="Assumption period" className="input" value={assume.payPeriod} onChange={(e) => setAssume({ ...assume, payPeriod: e.target.value })}><option>MONTHLY</option><option>ANNUAL</option><option>WEEKLY</option><option>DAILY</option><option>HOURLY</option></select></Field>
              </div>
              <Field label="Reasoning (required)"><textarea aria-label="Assumption reasoning" className="input mt-1 h-16 w-full" value={assume.reasoning} onChange={(e) => setAssume({ ...assume, reasoning: e.target.value })} /></Field>
              <div className="mt-3 flex gap-2">
                <button className="btn-primary" onClick={() => void createBaseline({ profileId: prof.id, lifeStage: prof.lifeStage, yearStart: prof.yearStart, yearEnd: prof.yearEnd, baselineType: "ASSUMPTION", low: assume.low, high: assume.high, point: assume.point, currency: assume.currency, payPeriod: assume.payPeriod, reasoning: assume.reasoning, occupation: prof.occupation })}>Save assumption</button>
                <button className="btn-ghost" onClick={() => setAssume(null)}>Cancel</button>
              </div>
            </section>
          )}

          <section className="panel mb-6">
            <div className="panel-header"><h3 className="text-base">Economic baselines</h3><Link to="/snapshots" className="btn-ghost text-xs">Dataset snapshots →</Link></div>
            <div className="divide-y divide-border">
              {baselines.map((b) => (
                <div key={b.id} className="px-4 py-3 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{b.lifeStageLabel} · {b.yearStart}–{b.yearEnd}</span>
                    <span className="chip border-border">{b.baselineType}</span>
                    <span className={cn("chip", confTone(b.confidence))}>{b.confidence}</span>
                    {b.userApproved ? <span className="chip border-pass text-pass">approved {b.approvedAt?.slice(0, 10)}</span> : <span className="chip border-warn text-warn">draft</span>}
                    {b.pinnedInSnapshot && <span className="chip border-fact text-fact">pinned</span>}
                    <div className="ml-auto flex gap-1">
                      <button className="btn text-xs" onClick={() => void run(() => api.approveBaseline(b.id, !b.userApproved))}>{b.userApproved ? "Withdraw approval" : "Approve"}</button>
                      <button className="btn-ghost text-xs" onClick={() => void run(() => api.deleteBaseline(b.id))}><Trash2 className="h-3 w-3" /></button>
                    </div>
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-4 text-xs">
                    <div>
                      <div className="eyebrow">Evidence-supported baseline</div>
                      <div className="data text-base">{range(b)} {b.currency}/{b.payPeriod.toLowerCase()} <span className="text-xs text-muted-foreground">{b.grossOrNet === "UNKNOWN" ? "gross/net unknown" : b.grossOrNet.toLowerCase()} · not take-home pay</span></div>
                      <div className="text-muted-foreground">{b.confidenceReasons.join(" · ")}</div>
                      {b.reasoning && <div className="mt-1">Reasoning: {b.reasoning}</div>}
                      {b.evidence.map((e) => <div key={e.wageObservationId} className="mt-1">Evidence {e.sourceYear}: {e.population} — {fmtWage(e.value)}{e.derivedValue && ` → CPI-adjusted ${fmtWage(e.derivedValue)} (fact ${e.derivedFactId})`} · score {e.score}</div>)}
                    </div>
                    <div>
                      <div className="eyebrow">Prototype income (Economic Ledger, annual) — not replaced</div>
                      {b.prototypeIncome.years.length === 0 ? <div className="text-muted-foreground">No prototype rows in these years.</div> :
                        b.prototypeIncome.years.map((y) => <div key={y.year} className="data">{y.year}: {fmtWage(String(y.income))} {y.currency}/yr <span className="chip ml-1 border-warn text-[10px] text-warn">PROTOTYPE</span></div>)}
                    </div>
                  </div>
                </div>
              ))}
              {baselines.length === 0 && <div className="px-4 py-6 text-xs text-muted-foreground">No baselines yet. Accept evidence or record an explicit assumption above.</div>}
            </div>
          </section>

          <section className="panel mb-6">
            <div className="panel-header"><h3 className="text-base">Evidence gaps</h3><button className="btn" onClick={() => void run(() => api.detectGaps(eid), "Gaps re-checked against stored evidence.")}><RefreshCw className="h-3.5 w-3.5" /> Detect gaps</button></div>
            <table className="tbl text-xs">
              <thead><tr><th>Priority</th><th>Gap</th><th>Reason</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {gaps.map((g) => (
                  <tr key={g.id}>
                    <td className={cn(g.priority === "HIGH" ? "text-fail" : "text-warn")}>{g.priority}</td><td className="font-medium">{g.title} <span className="text-muted-foreground">{g.country}</span></td><td>{g.reason}</td><td>{g.status}</td>
                    <td>{g.researchTaskId ? <Link to="/research" className="text-primary underline">Task {g.researchTaskId}</Link> : <button className="btn-ghost text-xs" onClick={() => void run(async () => { await api.gapToTask(g.id); await reload(); }, "Research task created (pending; no autonomous research runs).")}>Create research task</button>}</td>
                  </tr>
                ))}
                {gaps.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-muted-foreground">Run “Detect gaps” to list missing evidence.</td></tr>}
              </tbody>
            </table>
          </section>

          <section className="panel">
            <div className="panel-header"><h3 className="text-base">Household income structure</h3>
              <button className="btn-ghost text-xs" onClick={() => void run(() => api.createHousehold(eid, { label: `Household from ${ch.birthYear + 25}`, yearStart: ch.birthYear + 25, yearEnd: ch.birthYear + 65, members: [{ role: "self", name: ch.name }, { role: "spouse" }] }))}><Plus className="h-3 w-3" /> Add household</button>
            </div>
            <div className="p-4 text-xs">
              <p className="mb-2 text-muted-foreground">Structure only. Spouse income, remittances, pensions and investment income stay UNKNOWN until evidence or an explicit assumption exists. Taxes are a later phase.</p>
              {hh.map((h) => (
                <div key={h.id} className="mb-3 rounded-sm border border-border p-2">
                  <div className="font-medium">{h.label} · {h.yearStart}–{h.yearEnd}</div>
                  <div>Members: {h.members.map((m) => `${m.role}${m.name ? ` (${m.name})` : ""} — ${m.employmentKind}`).join("; ")}</div>
                  {h.streams.map((s) => <div key={s.id} className="flex items-center gap-2">{s.kind} {s.yearStart}–{s.yearEnd}: {s.low || s.high ? `${s.low ?? "…"}–${s.high ?? "…"} ${s.currency}` : "amount unknown"} · {s.basis} <button className="btn-ghost text-[10px]" onClick={() => void run(() => api.deleteStream(s.id))}>remove</button></div>)}
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(["employment", "self-employment", "remittance-sent", "remittance-received", "pension", "investment"] as const).map((k) => (
                      <button key={k} className="btn-ghost text-[10px]" onClick={() => { const b = baselines.find((x) => x.userApproved); void run(() => api.addStream(h.id, k === "employment" && b ? { kind: k, yearStart: b.yearStart, yearEnd: b.yearEnd, low: b.low ?? b.point, high: b.high ?? b.point, currency: b.currency, payPeriod: b.payPeriod, basis: b.baselineType, baselineId: b.id } : { kind: k, yearStart: h.yearStart, yearEnd: h.yearEnd })); }}>+ {k}{k === "employment" ? " (from approved baseline)" : ""}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
