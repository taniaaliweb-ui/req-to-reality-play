import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { ListPlus, RefreshCw } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, Field, PageHeader } from "@/components/lifespan/primitives";
import { ApiError, lifespanApi } from "@/services/lifespanApi";
import type { AssumptionRecord, CellStatus, Coverage, EvidenceGap, HistoricalEventRec, LifeMatrix, MatrixCell, MigrationPathEvidence, ReadinessV2 } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/life-evidence")({
  head: pageHead("Life Evidence", "Life Evidence Matrix: what is known, assumed and missing for every life stage, with simulation readiness."),
  component: LifeEvidence,
});

const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed.");
const statusCls: Record<string, string> = {
  READY: "border-pass/60 bg-pass/10 text-pass", PARTIAL: "border-warn/60 bg-warn/10 text-warn", MISSING: "border-fail/60 bg-fail/10 text-fail",
  NOT_READY: "border-fail/60 bg-fail/10 text-fail", NOT_APPLICABLE: "border-border text-muted-foreground",
};
const covCls: Record<Coverage, string> = { DIRECT: "bg-pass", NEARBY: "bg-pass/50", DERIVED: "bg-primary/60", ASSUMED: "bg-warn", MISSING: "bg-fail/70" };
const g = (o: unknown, k: string) => String((o as Record<string, unknown>)[k] ?? "");
const label = (s: string) => (s === "NOT_APPLICABLE" ? "n/a" : s.replace("_", " "));

function Chip({ s }: { s: string }) {
  return <span className={cn("chip", statusCls[s] ?? "border-border")}>{label(s)}</span>;
}

function CoverageBar({ cov }: { cov: { year: number; coverage: Coverage }[] }) {
  if (!cov.length) return null;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-sm border border-border" aria-label="Year coverage">
      {cov.map((c) => <div key={c.year} title={`${c.year}: ${c.coverage}`} className={cn("h-full flex-1", covCls[c.coverage])} />)}
    </div>
  );
}

function LifeEvidence() {
  const { active, mode } = useLifespan();
  const api = lifespanApi.life;
  const eid = active?.id;
  const [mx, setMx] = useState<LifeMatrix | null>(null);
  const [rd, setRd] = useState<ReadinessV2 | null>(null);
  const [asm, setAsm] = useState<AssumptionRecord[]>([]);
  const [gaps, setGaps] = useState<EvidenceGap[]>([]);
  const [paths, setPaths] = useState<MigrationPathEvidence[]>([]);
  const [events, setEvents] = useState<HistoricalEventRec[]>([]);
  const [sel, setSel] = useState<{ stage: string; domain: string } | null>(null);
  const [cell, setCell] = useState<MatrixCell | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ claim: "", value: "", unit: "", reason: "", yearStart: "", yearEnd: "" });

  const refresh = useCallback(async () => {
    if (!eid) return;
    setBusy(true);
    try {
      const [m, r, a, g, p, ev] = await Promise.all([api.matrix(eid), api.readiness(eid), api.assumptions(eid), lifespanApi.labor.gaps(eid), api.migrationPaths(eid), api.episodeEvents(eid)]);
      setMx(m); setRd(r); setAsm(a); setGaps(g.filter((x) => x.gapKey.startsWith("life:"))); setPaths(p); setEvents(ev.events.filter((e) => e.matches?.length));
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  }, [api, eid]);
  useEffect(() => {
    if (mode === "backend") void refresh();
  }, [mode, refresh]);
  useEffect(() => {
    if (!sel || !eid) return setCell(null);
    api.cell(eid, sel.stage, sel.domain).then((r) => setCell(r.cell)).catch((e) => setError(errMsg(e)));
  }, [sel, eid, api, asm, gaps]);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  if (mode !== "backend") return (<><PageHeader eyebrow="Evidence" title="Life Evidence" /><div className="panel p-6 text-sm text-muted-foreground">Requires the LifeSpan backend (start it with ./scripts/start-local.sh).</div></>);
  if (!active || !eid) return <EmptyEpisode />;
  const domains = mx?.domains ?? [];
  const selStage = mx?.stages.find((s) => s.stage === sel?.stage);

  return (
    <>
      <PageHeader eyebrow="Evidence · Life context" title="Life Evidence" description="What is known, assumed and missing for every stage of this life. Coverage shows whether evidence exists — not what will happen." />
      {error && <div className="mb-4 rounded-sm border border-fail/50 bg-fail/5 p-2 text-sm text-fail">{error}</div>}

      {rd && (
        <section className="panel mb-6 p-4">
          <div className="mb-3 flex items-center gap-3">
            <h3 className="text-base">Simulation readiness</h3><Chip s={rd.overall} />
            <button className="btn-ghost ml-auto text-xs" disabled={busy} onClick={() => void refresh()}><RefreshCw className="h-3 w-3" /> Refresh</button>
            <button className="btn text-xs" onClick={() => void run(() => api.detectGaps(eid))}>Detect evidence gaps</button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {rd.groups.map((g) => (
              <div key={g.key} className="flex items-center justify-between rounded-sm border border-border px-3 py-2 text-xs">
                <span>{g.label}{g.required && <span className="ml-1 text-muted-foreground">· required</span>}</span>
                <span className="flex items-center gap-2"><span className="data text-muted-foreground">{g.ready}/{g.partial}/{g.missing}</span><Chip s={g.status} /></span>
              </div>
            ))}
          </div>
          {rd.blocking.length > 0 && <p className="mt-3 text-xs text-fail">Blocking: {rd.blocking.join(" · ")}</p>}
          <p className="mt-2 text-[11px] text-muted-foreground">{rd.note}</p>
        </section>
      )}

      {mx && (
        <section className="panel mb-6 overflow-x-auto">
          <div className="panel-header"><h3 className="text-base">Life Evidence Matrix</h3><span className="text-[11px] text-muted-foreground">Click a cell for facts, candidates, assumptions, gaps and tasks</span></div>
          <table className="tbl text-xs">
            <thead><tr><th>Life stage</th><th>Status</th>{domains.map((d) => <th key={d.key} className="whitespace-nowrap">{d.label}</th>)}</tr></thead>
            <tbody>
              {mx.stages.map((s) => (
                <tr key={s.stage}>
                  <td className="whitespace-nowrap font-medium">{s.label}<div className="data text-[10px] text-muted-foreground">{s.yearStart}{s.yearEnd !== s.yearStart && `–${s.yearEnd}`} · {s.cities.join("/") || s.countries.join("/")}</div></td>
                  <td><Chip s={s.status} /></td>
                  {domains.map((d) => {
                    const c = s.cells.find((x) => x.domain === d.key);
                    if (!c) return <td key={d.key} className="text-muted-foreground">·</td>;
                    const on = sel?.stage === s.stage && sel?.domain === d.key;
                    return (
                      <td key={d.key}>
                        <button aria-label={`${s.label} ${d.label}`} onClick={() => setSel(on ? null : { stage: s.stage, domain: d.key })}
                          className={cn("w-24 space-y-1 rounded-sm border p-1 text-left", on ? "border-primary" : "border-transparent hover:border-border")}>
                          <span className={cn("chip text-[10px]", statusCls[c.status], c.critical && "font-semibold")}>{label(c.status)}{c.critical ? " *" : ""}</span>
                          <CoverageBar cov={c.coverage} />
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex flex-wrap gap-3 px-4 py-2 text-[11px] text-muted-foreground">
            {(Object.keys(covCls) as Coverage[]).map((k) => <span key={k} className="flex items-center gap-1"><span className={cn("inline-block h-2 w-3 rounded-sm", covCls[k])} />{k}</span>)}
            <span>* critical for the stage</span><span>{mx.note}</span>
          </div>
        </section>
      )}

      {sel && cell && selStage && (
        <section className="panel mb-6 p-4">
          <div className="mb-2 flex items-center gap-2"><h3 className="text-base">{selStage.label} · {cell.label}</h3><Chip s={cell.status} />
            <span className="text-xs text-muted-foreground">{selStage.yearStart}–{selStage.yearEnd} · validity window ±{cell.windowYears} yr — {cell.windowReason}</span></div>
          <ul className="mb-3 list-disc pl-5 text-xs text-muted-foreground">{cell.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Supporting evidence ({cell.supportingCount})</h4>
              <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-sm border border-border text-xs">
                {(cell.supporting ?? []).slice(0, 40).map((o, i) => (
                  <li key={String(o.id ?? i)} className="px-2 py-1.5">
                    {"metricLabel" in o && o.metricLabel ? (
                      <>
                        <div><span className="data">{o.year}</span> {o.metricLabel}: <span className="data font-medium">{o.value}</span> {o.unit} <span className="text-muted-foreground">· {o.country}{o.sex ? ` · ${o.sex}` : ""} · {o.observationType}</span></div>
                        <div className="text-[10px] text-muted-foreground">{o.provider} · Evidence Match Score {o.match?.score}/100 (not a probability) · population statistic</div>
                      </>
                    ) : (
                      <div>{g(o, "name") || g(o, "label") || g(o, "id")} {g(o, "relevance") && <span className="text-muted-foreground">· {g(o, "relevance")} · {g(o, "reason")} · {g(o, "verification")}</span>}</div>
                    )}
                  </li>
                ))}
                {!cell.supportingCount && <li className="px-2 py-2 text-muted-foreground">No evidence within the validity window. MISSING DATA.</li>}
              </ul>
              {!!cell.candidates?.length && (
                <>
                  <h4 className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide">Candidates outside window (not used)</h4>
                  <ul className="text-xs text-muted-foreground">{cell.candidates.map((o) => <li key={o.id}>{o.year} {o.metricLabel}: {o.value} {o.unit} — score {o.match?.score}</li>)}</ul>
                </>
              )}
              {!!cell.extra?.length && (
                <>
                  <h4 className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide">Policy / context / baselines</h4>
                  <ul className="text-xs">{cell.extra.map((x, i) => <li key={i}><span className="chip mr-1 text-[10px]">{g(x, "type")}</span>{g(x, "title") || g(x, "claim") || g(x, "id")} {g(x, "verification") && <span className="text-muted-foreground">({g(x, "verification")})</span>}</li>)}</ul>
                </>
              )}
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide">Assumptions</h4>
              <ul className="mb-2 text-xs">{(cell.assumptions ?? []).map((a) => <li key={a.id}>{a.claim} {a.value && `= ${a.value} ${a.unit}`} <span className="text-muted-foreground">({a.yearStart ?? "…"}–{a.yearEnd ?? "…"})</span></li>)}
                {!cell.assumptions?.length && <li className="text-muted-foreground">None.</li>}</ul>
              <div className="space-y-2 rounded-sm border border-border p-2">
                <Field label="Claim"><input aria-label="Assumption claim" className="input w-full" value={form.claim} onChange={(e) => setForm({ ...form, claim: e.target.value })} /></Field>
                <div className="flex gap-2">
                  <Field label="Value"><input className="input w-24" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} /></Field>
                  <Field label="Unit"><input className="input w-28" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} /></Field>
                  <Field label="From"><input className="input w-20" placeholder={String(selStage.yearStart)} value={form.yearStart} onChange={(e) => setForm({ ...form, yearStart: e.target.value })} /></Field>
                  <Field label="To"><input className="input w-20" placeholder={String(selStage.yearEnd)} value={form.yearEnd} onChange={(e) => setForm({ ...form, yearEnd: e.target.value })} /></Field>
                </div>
                <Field label="Reason (≥ 20 characters)"><textarea aria-label="Assumption reason" className="input h-14 w-full" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></Field>
                <button className="btn text-xs" disabled={form.claim.length < 5 || form.reason.length < 20}
                  onClick={() => void run(() => api.createAssumption(eid, { domain: cell.domain, lifeStage: sel.stage, claim: form.claim, value: form.value, unit: form.unit, reason: form.reason,
                    ...(form.yearStart ? { yearStart: Number(form.yearStart) } : {}), ...(form.yearEnd ? { yearEnd: Number(form.yearEnd) } : {}) }).then(() => setForm({ claim: "", value: "", unit: "", reason: "", yearStart: "", yearEnd: "" })))}>
                  Register explicit assumption
                </button>
              </div>
              <h4 className="mb-1 mt-3 text-xs font-semibold uppercase tracking-wide">Gaps & research tasks</h4>
              <ul className="text-xs">
                {(cell.gaps ?? []).map((g) => (
                  <li key={g.id} className="mb-1">{g.priority} · {g.status} · {g.reason}
                    {g.researchTaskId ? <span className="ml-1 text-pass">task {g.researchTaskId}</span> : g.status === "open" && <button className="btn-ghost ml-1 text-xs" onClick={() => void run(() => lifespanApi.labor.gapToTask(g.id))}><ListPlus className="h-3 w-3" /> Create research task</button>}
                  </li>
                ))}
                {!cell.gaps?.length && <li className="text-muted-foreground">No gap recorded — run “Detect evidence gaps”.</li>}
              </ul>
            </div>
          </div>
        </section>
      )}

      <div className="grid grid-cols-2 gap-6">
        <section className="panel">
          <div className="panel-header"><h3 className="text-base">Evidence gaps ({gaps.filter((g) => g.status === "open").length} open)</h3></div>
          <ul className="max-h-96 divide-y divide-border overflow-y-auto text-xs">
            {gaps.filter((g) => g.status === "open").map((g) => (
              <li key={g.id} className="flex items-start gap-2 px-4 py-2">
                <span className={cn("chip text-[10px]", g.priority === "HIGH" ? "border-fail text-fail" : g.priority === "MEDIUM" ? "border-warn text-warn" : "")}>{g.priority}</span>
                <div className="flex-1"><div>{g.title}</div><div className="text-[10px] text-muted-foreground">{g.targetPopulation}</div></div>
                {g.researchTaskId ? <span className="text-[10px] text-pass">task</span> : <button className="btn-ghost text-xs" onClick={() => void run(() => lifespanApi.labor.gapToTask(g.id))}>→ task</button>}
              </li>
            ))}
            {!gaps.length && <li className="px-4 py-3 text-muted-foreground">Run “Detect evidence gaps”.</li>}
          </ul>
        </section>
        <section className="panel">
          <div className="panel-header"><h3 className="text-base">Assumption Register ({asm.length})</h3></div>
          <table className="tbl text-xs">
            <thead><tr><th>Claim</th><th>Stage / domain</th><th>Status</th><th>Snapshot</th><th></th></tr></thead>
            <tbody>
              {asm.map((a) => (
                <tr key={a.id}>
                  <td>{a.claim} {a.value && <span className="data">= {a.value} {a.unit}</span>}<div className="text-[10px] text-muted-foreground">{a.reason.slice(0, 120)}</div></td>
                  <td>{a.lifeStage || "—"} / {a.domain}</td>
                  <td>{a.isPrototype ? <span className="text-warn">PROTOTYPE</span> : a.status}</td>
                  <td>{a.includedInSnapshots.length ? `${a.includedInSnapshots.length} final` : "—"}</td>
                  <td>{a.kind === "register" && a.status === "active" && <button className="btn-ghost text-xs" onClick={() => void run(() => api.retireAssumption(a.id))}>Retire</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel">
          <div className="panel-header"><h3 className="text-base">Migration path evidence</h3></div>
          {paths.map((p) => (
            <div key={p.id} className="space-y-1 px-4 py-3 text-xs">
              <div className="font-medium">{p.origin} → {p.destination} · {p.yearStart}–{p.yearEnd}</div>
              <div>{p.observations.length} migration observations · {p.policies.length} policies · destination wage years: {p.destinationWageYears.join(", ") || "none"}</div>
              <ul className="list-disc pl-5">{p.policies.map((x) => <li key={x.id}>{x.title} ({x.effectiveStart}–{x.effectiveEnd ?? ""}) <span className="text-muted-foreground">{x.verification}</span></li>)}</ul>
              {p.missing.map((x) => <div key={x} className="text-fail">MISSING: {x}</div>)}
              <div className="text-[10px] text-muted-foreground">{p.note}</div>
            </div>
          ))}
          {!paths.length && <p className="px-4 py-3 text-xs text-muted-foreground">No migration in this life.</p>}
        </section>
        <section className="panel">
          <div className="panel-header"><h3 className="text-base">Historical context matched to this life</h3></div>
          <ul className="max-h-96 divide-y divide-border overflow-y-auto text-xs">
            {events.map((e) => (
              <li key={e.id} className="px-4 py-2">
                <div className="font-medium">{e.name} <span className="data text-muted-foreground">{e.startDate}{e.endDate ? `–${e.endDate}` : ""}</span> {e.verification === "unverified" && <span className="chip ml-1 border-warn text-[10px] text-warn">unverified</span>}</div>
                <div className="text-muted-foreground">{e.matches?.map((m) => `${m.label}: ${m.relevance.replace("_", " ").toLowerCase()}`).join(" · ")}</div>
              </li>
            ))}
          </ul>
          <p className="px-4 py-2 text-[10px] text-muted-foreground">Relevance (place + period) only. Exposure and impact are decided in a later phase.</p>
        </section>
      </div>
    </>
  );
}
