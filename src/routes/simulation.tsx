import { createFileRoute } from "@tanstack/react-router";
import { Crown, GitBranch, Play, RefreshCw, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, PageHeader, Slider } from "@/components/lifespan/primitives";
import { BackendOnly, CoverageChip, ErrorLine, money, PriorNote, ProbClassChip, SimulatedLabel, useBackend } from "@/components/lifespan/sim";
import { CONTROL_LABELS } from "@/lib/defaults";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";
import { lifespanApi } from "@/services/lifespanApi";
import type { Lineage, SimEvent, SimJob, SimPrior, SimRun, SimState, WageStep } from "@/types/simulation";

export const Route = createFileRoute("/simulation")({
  head: pageHead("Simulation", "Run reproducible simulated lives from frozen evidence, assumptions and visible provisional priors."),
  component: Simulation,
});

const sim = lifespanApi.sim;
const CTL: Record<string, string> = { ...CONTROL_LABELS, careerVolatility: "Career volatility", relationshipVolatility: "Relationship volatility", healthIntensity: "Health-event intensity", outlierIntensity: "Outlier intensity" };
const TABS = ["Input review", "Run life", "Explore outcomes", "Branch & what-if", "Prior registry"] as const;

function Simulation() {
  const { active } = useLifespan();
  const [tab, setTab] = useState<(typeof TABS)[number]>("Input review");
  const [runId, setRunId] = useState<string | null>(null);
  if (!active) return <EmptyEpisode />;
  return (
    <>
      <PageHeader eyebrow="Pipeline · 5–7" title="Simulation Engine" description="Year-by-year simulated life from a finalized snapshot. Every outcome is SIMULATED and fully traceable." />
      <BackendOnly>
        <div className="mb-4 flex flex-wrap gap-1 border-b border-border">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)} className={cn("px-3 py-2 text-sm", tab === t ? "border-b-2 border-primary font-medium" : "text-muted-foreground")}>{t}</button>
          ))}
        </div>
        {tab === "Input review" && <Review eid={active.id} onRun={(id) => { setRunId(id); setTab("Run life"); }} />}
        {tab === "Run life" && <Runs eid={active.id} runId={runId} setRunId={setRunId} />}
        {tab === "Explore outcomes" && <Outcomes eid={active.id} open={(id) => { setRunId(id); setTab("Run life"); }} />}
        {tab === "Branch & what-if" && <Branches eid={active.id} runId={runId} open={(id) => { setRunId(id); setTab("Run life"); }} />}
        {tab === "Prior registry" && <Priors />}
      </BackendOnly>
    </>
  );
}

function Review({ eid, onRun }: { eid: string; onRun: (id: string) => void }) {
  const { data: rv, error, refresh } = useBackend(() => sim.review(eid), [eid]);
  const [ack, setAck] = useState(false);
  const [seed, setSeed] = useState(20260101);
  const [cfg, setCfg] = useState<Record<string, number>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (rv) setCfg(rv.config); }, [rv]);
  if (error) return <><ErrorLine msg={error} /><button className="btn-ghost" onClick={() => void refresh()}><RefreshCw className="h-4 w-4" /> Retry</button></>;
  if (!rv) return <div className="text-sm text-muted-foreground">Loading input review…</div>;
  const go = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const inp = await sim.createInput(eid, { masterSeed: seed, acknowledged: ack, config: cfg });
      const r = await sim.run({ inputId: inp.id, seed });
      onRun(r.id);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_300px]">
      <section className="panel">
        <div className="panel-header"><div><div className="font-serif text-lg">Simulation Input Review</div><div className="text-xs text-muted-foreground">Snapshot “{rv.snapshot.label}” v{rv.snapshot.version} · {rv.note}</div></div></div>
        <table className="w-full text-sm">
          <thead className="text-left text-[11px] uppercase tracking-wide text-muted-foreground"><tr><th className="p-2">Dimension</th><th>Evidence coverage</th><th>Simulation coverage</th><th>Resolution</th></tr></thead>
          <tbody>
            {rv.dimensions.map((d) => (
              <tr key={d.key} className="border-t border-border align-top">
                <td className="p-2 font-medium">{d.label}{d.critical && <span className="ml-1 text-[10px] text-muted-foreground">critical</span>}<div className="text-[11px] font-normal text-muted-foreground">{d.reasons.join(" ")}</div></td>
                <td className="p-2"><CoverageChip s={d.evidenceStatus} /></td>
                <td className="p-2"><CoverageChip s={d.simulationStatus} /></td>
                <td className="p-2 text-xs">{d.resolution.length ? d.resolution.map((r) => <div key={r}>→ {r}</div>) : "—"}{d.unusableAssumptionIds.length > 0 && <div className="text-warn">Not machine-readable: {d.unusableAssumptionIds.join(", ")}</div>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rv.blocked.length > 0 && <div className="m-3 rounded-sm border border-fail/50 bg-fail/5 p-3 text-sm text-fail"><b>BLOCKED.</b> {rv.blocked.map((b) => <div key={b}>• {b}</div>)}<div className="mt-1 text-xs text-muted-foreground">Add the assumption or baseline, then create and finalize a new snapshot.</div></div>}
        <div className="p-3 text-xs text-muted-foreground"><PriorNote /> · {rv.locks.length} locked timeline event(s) will be preserved.</div>
      </section>
      <aside className="panel h-fit space-y-3 p-4">
        <label className="block"><span className="field-label">Master seed</span><input type="number" className="input data" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label>
        {Object.keys(CTL).map((k) => <Slider key={k} label={CTL[k] ?? k} value={cfg[k] ?? 50} onChange={(n) => setCfg({ ...cfg, [k]: n })} />)}
        <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I acknowledge that {rv.needsAcknowledgement.length} dimension(s) rely on partial evidence, assumptions or provisional priors.</label>
        <ErrorLine msg={msg} />
        <button className="btn-primary w-full justify-center" disabled={!rv.canRun || busy} onClick={() => void go()}><Play className="h-4 w-4" /> {busy ? "Simulating…" : "Run Life"}</button>
      </aside>
    </div>
  );
}

function Runs({ eid, runId, setRunId }: { eid: string; runId: string | null; setRunId: (s: string) => void }) {
  const { data: runs, refresh } = useBackend(() => sim.runs(eid), [eid, runId]);
  const { data: can, refresh: refreshCan } = useBackend(() => sim.canonical(eid), [eid]);
  const id = runId ?? can?.canonical?.id ?? runs?.[0]?.id ?? null;
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_1fr]">
      <aside className="panel h-fit max-h-[70vh] overflow-auto">
        <div className="panel-header text-sm font-medium">Runs</div>
        {can?.stale && <div className="m-2 rounded-sm border border-warn/50 bg-assumption-soft p-2 text-xs">{can.message} ({can.reasons.join(", ")})</div>}
        {(runs ?? []).map((r) => (
          <button key={r.id} onClick={() => setRunId(r.id)} className={cn("block w-full border-t border-border px-3 py-2 text-left text-xs hover:bg-accent", r.id === id && "bg-sim-soft")}>
            <div className="data">{r.id}{r.isCanonical && <Crown className="ml-1 inline h-3 w-3 text-warn" />}</div>
            <div className="text-muted-foreground">{r.kind} · seed {r.seed} · died {r.outcome.deathAge ?? "—"}</div>
          </button>
        ))}
        {runs?.length === 0 && <div className="p-3 text-xs text-muted-foreground">No runs yet. Use Input review → Run Life.</div>}
      </aside>
      {id ? <RunView id={id} onChanged={() => { void refresh(); void refreshCan(); }} /> : <div className="panel p-6 text-sm text-muted-foreground">No simulation selected.</div>}
    </div>
  );
}

function RunView({ id, onChanged }: { id: string; onChanged: () => void }) {
  const { reload } = useLifespan();
  const { data: run, error, refresh } = useBackend(() => sim.getRun(id), [id]);
  const { data: evs, refresh: refreshEv } = useBackend(() => sim.events(id), [id]);
  const { data: states, refresh: refreshSt } = useBackend(() => sim.states(id), [id]);
  const [why, setWhy] = useState<SimEvent | null>(null);
  const [showNon, setShowNon] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  if (error) return <ErrorLine msg={error} />;
  if (!run) return <div className="text-sm text-muted-foreground">Loading run…</div>;
  const o = run.outcome;
  const canonical = async () => {
    try {
      await sim.setCanonical(id);
      await refresh(); await refreshEv(); await refreshSt();
      await reload();
      onChanged();
      setMsg("Set as Canonical Life — simulated events were added to the Timeline (labelled SIMULATED). Alternative runs are kept.");
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const errs = run.audit.filter((a) => a.severity === "error").length;
  const shown = (evs ?? []).filter((e) => (showNon ? true : e.occurred && e.importance >= 2));
  return (
    <section className="space-y-4">
      <div className="panel p-4">
        <div className="flex flex-wrap items-center gap-2"><span className="font-serif text-lg">{run.label || run.id}</span><SimulatedLabel />{run.isCanonical && <span className="chip border-warn/50 text-warn">Canonical life</span>}
          {run.overrides.length > 0 && <span className="chip border-warn/50 bg-assumption-soft">SCENARIO OVERRIDE: {run.overrides.map((x) => x.type).join(", ")}</span>}
          <span className="ml-auto" />{!run.isCanonical && <button className="btn-primary" onClick={() => void canonical()}><Crown className="h-4 w-4" /> Set as Canonical Life</button>}</div>
        <div className="mt-1 text-xs text-muted-foreground">seed {run.seed} · engine {run.engineVersion} · input {run.inputId} · fingerprint <span className="data">{o.fingerprint.slice(0, 12)}</span> · audit {errs} error(s), {run.audit.length - errs} warning(s)</div>
        {msg && <div className="mt-2 text-xs text-pass">{msg}</div>}
        <div className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
          <K label="Death age" v={o.deathAge ?? "alive"} /><K label="Lifetime earnings" v={money(o.lifetimeEarnings)} /><K label="Net worth at death" v={money(o.netWorthAtDeath)} /><K label="Peak net worth" v={money(o.peakNetWorth)} />
          <K label="Years employed / unemployed" v={`${o.yearsEmployed} / ${o.yearsUnemployed}`} /><K label="Retirement age" v={o.retirementAge ?? "—"} /><K label="Children" v={o.children} /><K label="Countries" v={o.countries.join(" → ")} />
          <K label="Education" v={o.education} /><K label="Home owner" v={o.homeOwner ? "yes" : "no"} /><K label="Business" v={o.businessAttempt ? (o.businessSuccess ? "succeeded" : "attempted") : "none"} /><K label="Economic position" v={o.economicPosition ?? "—"} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="panel max-h-[60vh] overflow-auto">
          <div className="panel-header text-sm"><span>Events — click for “See why”</span><label className="text-xs"><input type="checkbox" checked={showNon} onChange={(e) => setShowNon(e.target.checked)} /> include “see why not” & minor</label></div>
          {shown.map((e) => (
            <button key={e.id} onClick={() => setWhy(e)} className={cn("flex w-full gap-2 border-t border-border px-3 py-1.5 text-left text-xs hover:bg-accent", why?.id === e.id && "bg-accent", !e.occurred && "text-muted-foreground")}>
              <span className="data w-16 shrink-0">{e.year} · {e.age}</span><span className="flex-1">{e.occurred ? "" : "✕ "}{e.eventType.replaceAll("_", " ")}{e.scenarioOverride && " (override)"}{e.outcome === "FORCED" && " (locked)"}</span>
              <span className="data">{e.probability != null ? `${(e.probability * 100).toFixed(1)}%` : ""}</span>
            </button>
          ))}
        </div>
        <div className="panel p-4 text-sm">
          {why ? (
            <>
              <div className="mb-2 flex flex-wrap items-center gap-2"><span className="font-medium">{why.eventType.replaceAll("_", " ")} · {why.year} (age {why.age})</span><ProbClassChip c={why.probabilityClass} /><span className="chip">{why.outcome}</span></div>
              <pre className="whitespace-pre-wrap font-mono text-[11px] leading-5">{why.explanation}</pre>
              <div className="mt-2 space-y-1 text-[11px] text-muted-foreground">
                {why.evidenceIds.length > 0 && <div>Evidence: <span className="data">{why.evidenceIds.join(", ")}</span></div>}
                {why.assumptionIds.length > 0 && <div>Assumptions: <span className="data">{why.assumptionIds.join(", ")}</span></div>}
                {why.priorIds.length > 0 && <div>Priors: <span className="data">{why.priorIds.join(", ")}</span> <PriorNote /></div>}
                {why.factIds.length > 0 && <div>Locked/fact refs: <span className="data">{why.factIds.join(", ")}</span></div>}
                <div>Rule {why.ruleId}</div>
              </div>
              {why.lineage && <LineageView l={why.lineage} />}
            </>
          ) : <div className="text-muted-foreground">Select an event to see its full probability trace: base → modifiers → final probability → random draw → outcome.</div>}
        </div>
      </div>
      <Ledger states={states ?? []} />
      <Quality run={run} />
    </section>
  );
}

const K = ({ label, v }: { label: string; v: React.ReactNode }) => <div><div className="field-label">{label}</div><div className="data text-sm">{v}</div></div>;

function WageChain({ chain, coverage }: { chain: WageStep[]; coverage?: string | undefined }) {
  return (
    <table className="w-full text-[11px]">
      <thead className="text-left text-muted-foreground"><tr><th className="p-1">Step</th><th>Detail</th><th className="text-right">Value / factor</th><th>Classification</th></tr></thead>
      <tbody>
        {chain.map((c, i) => (
          <tr key={i} className="border-t border-border align-top">
            <td className="p-1 data">{c.step}</td><td>{c.label}{c.coverage ? ` · coverage ${c.coverage}` : ""}</td>
            <td className="data text-right">{c.value ? `${c.currency ?? ""} ${Number(c.value).toLocaleString()}` : c.factor ? `× ${Number(c.factor).toFixed(4)}` : ""}</td>
            <td><span className={cn("chip text-[9px]", c.classification === "SIMULATED" ? "text-sim" : c.classification === "EMPIRICAL" || c.classification === "DERIVED_FROM_EMPIRICAL" ? "text-pass" : "text-mock")}>{c.classification}</span></td>
          </tr>
        ))}
        {coverage && <tr><td colSpan={4} className="p-1 text-muted-foreground">Starting anchor coverage: {coverage}. The final wage is SIMULATED; it is evidence-derived only if every step above is EMPIRICAL/DERIVED.</td></tr>}
      </tbody>
    </table>
  );
}

function LineageView({ l }: { l: Lineage }) {
  if (l.kind === "WAGE_DERIVATION" && l.chain) return <div className="mt-3 border-t border-border pt-2"><div className="field-label mb-1">Wage derivation</div><WageChain chain={l.chain} coverage={l.anchorCoverage} /></div>;
  return (
    <div className="mt-3 border-t border-border pt-2 text-[11px]">
      <div className="field-label mb-1">Mortality lineage · {l.method}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        <span>Country / year</span><span className="data">{l.country} {l.year} (source year {l.sourceYear ?? "—"}{l.projection ? ", projection" : ""})</span>
        <span>Sex / age</span><span className="data">{l.sex} · {l.age} · group {l.ageGroup}</span>
        <span>Source</span><span className="data">{l.sourceIndicator} = {l.sourceValue ?? "—"}</span>
        <span>Formula</span><span className="data">{l.formula} ({l.formulaId} v{l.formulaVersion})</span>
        <span>Annual probability</span><span className="data">{l.annualProbability?.toFixed(6)}{l.finalAnnualProbability !== undefined ? ` → after modifiers ${l.finalAnnualProbability.toFixed(6)}` : ""}</span>
        <span>Observations</span><span className="data truncate">{(l.observationIds ?? []).join(", ")}</span>
      </div>
      {l.ageSpecificAvailable === false && <div className="mt-1 text-warn">No age-specific life table in the snapshot for this year — broad fallback used. Sync UN life tables in Life Context Data and re-snapshot.</div>}
    </div>
  );
}

function Ledger({ states }: { states: SimState[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const sel = states.find((s) => s.year === open);
  return (<>
    <div className="panel max-h-[50vh] overflow-auto">
      <div className="panel-header text-sm">Year-by-year economics <SimulatedLabel /></div>
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-card text-left text-muted-foreground"><tr><th className="p-1.5">Year</th><th>Age</th><th>Country</th><th>Status</th><th className="text-right">Income</th><th className="text-right">Expenses</th><th className="text-right">Net worth</th><th>Wage basis</th><th>Reconciled</th></tr></thead>
        <tbody>
          {states.map((s) => {
            const r = s.economics.reconciliation[s.currency];
            return (
              <tr key={s.year} className="border-t border-border">
                <td className="data p-1.5">{s.year}</td><td className="data">{s.age}</td><td>{s.country}</td><td>{s.economics.dependent ? "dependant" : s.employment}</td>
                <td className="data text-right">{s.currency} {Math.round(Number(s.economics.totalIncome)).toLocaleString()}</td>
                <td className="data text-right">{Math.round(Number(s.economics.totalExpenses)).toLocaleString()}</td>
                <td className="data text-right">{Math.round(Number(s.netWorth)).toLocaleString()}</td>
                <td>{s.economics.wageProvenance ? <button title="Show wage derivation" onClick={() => setOpen(open === s.year ? null : s.year)}><ProbClassChip c={s.economics.wageProvenance.class} /></button> : ""}</td>
                <td className={cn("data", r && Number(r.difference) !== 0 ? "text-fail" : "text-pass")}>{r ? (Number(r.difference) === 0 ? "✓" : r.difference) : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    {sel?.economics.wageProvenance?.chain && <div className="panel mt-2 p-3"><div className="mb-1 text-sm font-medium">Wage derivation {sel.year}</div><WageChain chain={sel.economics.wageProvenance.chain} coverage={sel.economics.wageProvenance.anchorCoverage} /></div>}
  </>);
}

function Quality({ run }: { run: SimRun }) {
  const q = run.qualityReport as Record<string, Record<string, unknown>>;
  return (
    <div className="panel p-4 text-xs">
      <div className="mb-2 text-sm font-medium">Simulation Quality Report <span className="text-muted-foreground">(no single accuracy score)</span></div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {Object.entries(q).filter(([k]) => k !== "note").map(([k, v]) => (
          <div key={k}><div className="field-label">{k.replace(/([A-Z])/g, " $1")}</div><pre className="whitespace-pre-wrap font-mono text-[10px]">{JSON.stringify(v, null, 1).slice(0, 900)}</pre></div>
        ))}
      </div>
      {run.audit.length > 0 && <div className="mt-3"><div className="field-label">Simulation audit</div>{run.audit.map((a, i) => <div key={i} className={a.severity === "error" ? "text-fail" : "text-warn"}>{a.severity.toUpperCase()} {a.ruleId}: {a.message}</div>)}</div>}
    </div>
  );
}

function Outcomes({ eid, open }: { eid: string; open: (id: string) => void }) {
  const { data: inputs } = useBackend(() => sim.inputs(eid), [eid]);
  const { data: jobs, refresh } = useBackend(() => sim.jobs(eid), [eid]);
  const [n, setN] = useState(50);
  const [job, setJob] = useState<SimJob | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { if (!job && jobs?.length) setJob(jobs[0]!); }, [jobs, job]);
  useEffect(() => {
    if (!job || !["QUEUED", "RUNNING"].includes(job.status)) return;
    const t = setTimeout(async () => setJob(await sim.job(job.id)), 700);
    return () => clearTimeout(t);
  }, [job]);
  const start = async () => {
    const inp = inputs?.[0];
    if (!inp) return setMsg("Create a simulation input first (Input review → Run Life).");
    try { setJob(await sim.startBatch(inp.id, n)); setMsg(null); void refresh(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const r = job?.result;
  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-center gap-3 p-4 text-sm">
        <span>Explore Outcomes from the latest input{inputs?.[0] ? ` (${inputs[0].id}, master seed ${inputs[0].masterSeed})` : ""}:</span>
        <select className="input w-24" value={n} onChange={(e) => setN(Number(e.target.value))}>{[10, 25, 50, 100, 250, 500].map((x) => <option key={x}>{x}</option>)}</select>
        <button className="btn-primary" onClick={() => void start()}><Play className="h-4 w-4" /> Run {n} lives</button>
        {job && ["QUEUED", "RUNNING"].includes(job.status) && <><div className="h-2 w-40 rounded bg-muted"><div className="h-2 rounded bg-primary" style={{ width: `${job.progress * 100}%` }} /></div><span className="data">{job.done}/{job.total}</span><button className="btn-ghost" onClick={() => void sim.cancelJob(job.id).then(setJob)}><Square className="h-3 w-3" /> Cancel</button></>}
        {job && <span className="chip">{job.status}</span>}
        <ErrorLine msg={msg ?? job?.error ?? null} />
      </div>
      {r && (
        <>
          <div className="rounded-sm border border-warn/50 bg-assumption-soft px-3 py-2 text-xs">{r.disclaimer}</div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="panel p-4 text-xs">
              <div className="mb-2 text-sm font-medium">Distributions ({r.runs} runs)</div>
              <table className="w-full"><thead className="text-muted-foreground"><tr><th className="text-left">Metric</th><th>p10</th><th>median</th><th>p90</th><th>min–max</th></tr></thead><tbody>
                {(["deathAge", "yearsEmployed", "yearsUnemployed", "retirementAge", "children"] as const).map((k) => r[k] && <tr key={k} className="border-t border-border"><td className="py-1">{k}</td><td className="data text-center">{r[k]!.p10}</td><td className="data text-center">{r[k]!.median}</td><td className="data text-center">{r[k]!.p90}</td><td className="data text-center">{r[k]!.min}–{r[k]!.max}</td></tr>)}
                {Object.entries(r.money).flatMap(([k, per]) => Object.entries(per).map(([c, s]) => s && <tr key={k + c} className="border-t border-border"><td className="py-1">{k} ({c})</td><td className="data text-center">{Math.round(s.p10).toLocaleString()}</td><td className="data text-center">{Math.round(s.median).toLocaleString()}</td><td className="data text-center">{Math.round(s.p90).toLocaleString()}</td><td className="data text-center">n={s.n}</td></tr>))}
              </tbody></table>
            </div>
            <div className="panel space-y-2 p-4 text-xs">
              <div className="text-sm font-medium">Rates</div>
              {Object.entries(r.rates).map(([k, v]) => <div key={k} className="flex justify-between"><span>{k}</span><span className="data">{(v * 100).toFixed(0)}%</span></div>)}
              <div className="pt-2 text-sm font-medium">Outliers observed</div>
              {Object.entries(r.outliers).map(([k, v]) => <div key={k} className="flex justify-between"><span>{k}</span><span className="data">{v}</span></div>)}
              {r.representative && <><div className="pt-2 text-sm font-medium">Representative runs</div><div className="text-muted-foreground">{r.representative.note}</div>
                <div className="flex flex-wrap gap-2">{(["median", "strong", "weak", "unusual"] as const).map((k) => <button key={k} className="btn-ghost" onClick={() => void sim.materialize(r.representative![k]).then(() => open(r.representative![k]))}>{k} outcome</button>)}</div></>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Branches({ eid, runId, open }: { eid: string; runId: string | null; open: (id: string) => void }) {
  const { data: can } = useBackend(() => sim.canonical(eid), [eid]);
  const parent = runId ?? can?.canonical?.id ?? null;
  const [year, setYear] = useState(2004);
  const [ov, setOv] = useState("no_migration");
  const [cmp, setCmp] = useState<Awaited<ReturnType<typeof sim.compare>> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [seed, setSeed] = useState(1);
  const go = async (kind: "branch" | "whatif" | "regen") => {
    setMsg(null);
    try {
      if (kind === "regen") { const r = await sim.regenerate(eid, { seed, acknowledged: true }); return open(r.id); }
      if (!parent) return setMsg("Select a run first.");
      if (kind === "whatif") { const p = await sim.getRun(parent); const r = await sim.run({ inputId: p.inputId, seed: p.seed, overrides: [{ type: ov }] }); return open(r.id); }
      const b = await sim.branch(parent, { year, overrides: ov ? [{ type: ov }] : [] });
      setCmp(await sim.compare(parent, b.id));
      setMsg(`Branch ${b.id} created from ${parent} at ${year}.`);
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <div className="panel space-y-3 p-4 text-sm">
        <div className="font-medium"><GitBranch className="mr-1 inline h-4 w-4" />Branch / What-if from {parent ?? "—"}</div>
        <label className="block"><span className="field-label">Branch year (history before it stays identical)</span><input type="number" className="input data" value={year} onChange={(e) => setYear(Number(e.target.value))} /></label>
        <label className="block"><span className="field-label">SCENARIO OVERRIDE</span><select className="input" value={ov} onChange={(e) => setOv(e.target.value)}><option value="">none (same seed → identical)</option>{["no_migration", "attends_university", "starts_business", "no_marriage", "retires_early"].map((x) => <option key={x}>{x}</option>)}</select></label>
        <div className="flex flex-wrap gap-2"><button className="btn-primary" onClick={() => void go("branch")}>Create branch</button><button className="btn-ghost" onClick={() => void go("whatif")}>Whole-life what-if</button></div>
        <hr className="border-border" />
        <div className="font-medium">Regenerate unlocked</div>
        <div className="text-xs text-muted-foreground">Keeps locked timeline events, builds a new frozen input from the latest finalized snapshot, stores a new run (nothing overwritten).</div>
        <div className="flex gap-2"><input type="number" className="input data w-32" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /><button className="btn-ghost" onClick={() => void go("regen")}><RefreshCw className="h-4 w-4" /> Regenerate</button></div>
        <ErrorLine msg={msg && !msg.startsWith("Branch") ? msg : null} />{msg?.startsWith("Branch") && <div className="text-xs text-pass">{msg}</div>}
      </div>
      {cmp && (
        <div className="panel p-4 text-xs">
          <div className="mb-2 text-sm font-medium">Branch comparison — first divergent year: {cmp.firstDivergentYear ?? "none"}</div>
          <table className="w-full"><tbody>{Object.entries(cmp.outcomes).map(([k, v]) => <tr key={k} className="border-t border-border"><td className="py-1">{k}</td><td className="data">{JSON.stringify(v.a)}</td><td className="data">{JSON.stringify(v.b)}</td></tr>)}</tbody></table>
          <div className="mt-2 grid grid-cols-2 gap-2"><div><div className="field-label">Only in parent</div>{cmp.eventsOnlyInA.map((x) => <div key={x}>{x}</div>)}</div><div><div className="field-label">Only in branch</div>{cmp.eventsOnlyInB.map((x) => <div key={x}>{x}</div>)}</div></div>
        </div>
      )}
    </div>
  );
}

function Priors() {
  const { data, error, refresh } = useBackend(() => sim.priors(), []);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const save = async (p: SimPrior, patch: { enabled?: boolean; parameter?: Record<string, unknown> }) => {
    try { await sim.updatePrior(p.key, patch); setMsg(`${p.key} saved as a new version (old inputs keep the old version).`); await refresh(); } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  if (error) return <ErrorLine msg={error} />;
  return (
    <div className="space-y-2">
      <div className="rounded-sm border border-mock/40 bg-mock-soft px-3 py-2 text-xs text-mock">{data?.label} — visible, editable, versioned. Registry version <span className="data">{data?.registryVersion}</span>. Future research can replace these with evidence.</div>
      {msg && <div className="text-xs">{msg}</div>}
      {(data?.priors ?? []).map((p) => (
        <div key={p.id} className={cn("panel p-3 text-xs", !p.enabled && "opacity-60")}>
          <div className="flex flex-wrap items-center gap-2"><span className="data font-medium">{p.id}</span><span className="chip">{p.domain}</span><span className="font-medium">{p.name}</span>
            {p.classification && <span className={cn("chip text-[10px]", p.classification === "PROVISIONAL_MODEL_PRIOR" ? "text-mock" : p.classification === "DETERMINISTIC_ACCOUNTING_RULE" ? "text-muted-foreground" : "text-pass")}>{p.classification}</span>}
            <label className="ml-auto flex items-center gap-1"><input type="checkbox" checked={p.enabled} onChange={(e) => void save(p, { enabled: e.target.checked })} /> enabled for simulation</label></div>
          <div className="mt-1 text-muted-foreground">{p.description} {p.notes}</div>
          <div className="mt-1 text-[11px] text-muted-foreground">Provenance: {p.provenance ?? "—"}{p.units && Object.keys(p.units).length > 0 && <> · Units: <span className="data">{Object.entries(p.units).map(([k, u]) => `${k}: ${u}`).join("; ")}</span></>} · version {p.version}</div>
          <textarea className="input data mt-2 h-20 w-full text-[11px]" value={edit[p.key] ?? JSON.stringify(p.parameter)} onChange={(e) => setEdit({ ...edit, [p.key]: e.target.value })} />
          {edit[p.key] !== undefined && <button className="btn-ghost mt-1" onClick={() => { try { void save(p, { parameter: JSON.parse(edit[p.key]!) }); setEdit({ ...edit, [p.key]: undefined as unknown as string }); } catch { setMsg("Parameter must be valid JSON."); } }}>Save new version</button>}
        </div>
      ))}
    </div>
  );
}
