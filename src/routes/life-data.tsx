import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { Download, Upload } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { Field, PageHeader } from "@/components/lifespan/primitives";
import { ApiError, lifespanApi, type ImportProvider } from "@/services/lifespanApi";
import type { ContextRec, HistoricalEventRec, LifeImportPreview, LifeObsSummary, PolicyRec } from "@/types/lifespan";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/life-data")({
  head: pageHead("Life Context Data", "UN population data, World Bank context indicators, official imports, policies, historical events and qualitative context."),
  component: LifeData,
});

const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed.");
const WB_CONTEXT = ["SE.PRM.ENRR", "SE.SEC.ENRR", "SE.TER.ENRR", "SE.PRM.CMPT.ZS", "SE.ADT.LITR.ZS", "SP.URB.TOTL.IN.ZS", "SP.RUR.TOTL.ZS", "SL.UEM.TOTL.ZS",
  "SL.TLF.CACT.ZS", "SP.DYN.LE00.MA.IN", "SP.DYN.IMRT.IN", "SP.DYN.TFRT.IN", "SM.POP.TOTL", "SM.POP.NETM", "BX.TRF.PWKR.CD.DT", "SP.POP.65UP.TO.ZS"];

function LifeData() {
  const { mode } = useLifespan();
  const api = lifespanApi.life;
  const [summary, setSummary] = useState<LifeObsSummary[]>([]);
  const [events, setEvents] = useState<HistoricalEventRec[]>([]);
  const [policies, setPolicies] = useState<PolicyRec[]>([]);
  const [context, setContext] = useState<ContextRec[]>([]);
  const [countries, setCountries] = useState("IND,ARE");
  const [years, setYears] = useState({ start: 1960, end: 2060 });
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [csv, setCsv] = useState("");
  const [prov, setProv] = useState<ImportProvider>("india-mospi");
  const [preview, setPreview] = useState<LifeImportPreview | null>(null);
  const [ctx, setCtx] = useState({ topic: "marriage-norms", country: "IND", yearStart: 1990, yearEnd: 2000, populationScope: "", claim: "", source: "", sourceUrl: "", evidenceType: "QUALITATIVE" });

  const refresh = useCallback(async () => {
    try {
      const [s, e, p, c] = await Promise.all([api.summary(), api.events(), api.policies(), api.context()]);
      setSummary(s); setEvents(e); setPolicies(p); setContext(c);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [api]);
  useEffect(() => {
    if (mode === "backend") void refresh();
  }, [mode, refresh]);
  const run = async (fn: () => Promise<string | void>) => {
    setError(null); setMsg(null); setBusy(true);
    try {
      const m = await fn();
      if (m) setMsg(m);
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const iso3 = countries.split(",").map((c) => c.trim().toUpperCase()).filter(Boolean);

  if (mode !== "backend") return (<><PageHeader eyebrow="Data" title="Life Context Data" /><div className="panel p-6 text-sm text-muted-foreground">Requires the LifeSpan backend (start it with ./scripts/start-local.sh).</div></>);

  return (
    <>
      <PageHeader eyebrow="Data · Free official sources" title="Life Context Data" description="Population statistics describe populations, never an individual's destiny. Missing data stays missing." />
      {error && <div className="mb-4 rounded-sm border border-fail/50 bg-fail/5 p-2 text-sm text-fail">{error}</div>}
      {msg && <div className="mb-4 rounded-sm border border-pass/50 bg-pass/5 p-2 text-sm text-pass">{msg}</div>}

      <section className="panel mb-6 space-y-3 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Countries (ISO3)"><input aria-label="Countries" className="input w-40" value={countries} onChange={(e) => setCountries(e.target.value)} /></Field>
          <Field label="From"><input type="number" className="input w-24" value={years.start} onChange={(e) => setYears({ ...years, start: Number(e.target.value) })} /></Field>
          <Field label="To"><input type="number" className="input w-24" value={years.end} onChange={(e) => setYears({ ...years, end: Number(e.target.value) })} /></Field>
          <button className="btn-primary" disabled={busy} onClick={() => void run(async () => {
            const r = await api.syncUnWpp({ countries: iso3, yearStart: years.start, yearEnd: years.end });
            return `UN WPP: ${r.retrieved} values stored (${r.projections} labelled PROJECTION), ${r.unavailable} unavailable.`;
          })}><Download className="h-4 w-4" /> Fetch UN World Population Prospects</button>
          <button className="btn" disabled={busy} onClick={() => void run(async () => {
            const iso2 = iso3.map((c) => ({ IND: "IN", ARE: "AE" } as Record<string, string>)[c] ?? c);
            const r = await lifespanApi.truth.syncWorldBank({ indicators: WB_CONTEXT, countries: iso2, yearStart: Math.max(1960, years.start), yearEnd: Math.min(2024, years.end) });
            return `World Bank context indicators: ${r.retrieved} values, ${r.unavailable} unavailable (left missing).`;
          })}><Download className="h-4 w-4" /> Fetch World Bank context indicators</button>
        </div>
        <p className="text-[11px] text-muted-foreground">UN WPP uses the official free bulk CSV (downloaded once, then works offline). The WPP Data Portal API needs a registered token, so it is not used. Years after 2023 are UN projections.</p>
      </section>

      <section className="panel mb-6">
        <div className="panel-header"><h3 className="text-base">Stored life-context observations</h3></div>
        <table className="tbl text-xs">
          <thead><tr><th>Domain</th><th>Country</th><th>Provider</th><th>Values</th><th>Years</th></tr></thead>
          <tbody>{summary.map((s) => <tr key={`${s.domain}${s.country}${s.provider}`}><td>{s.domain}</td><td>{s.country}</td><td>{s.provider}</td><td className="data">{s.count}</td><td className="data">{s.yearMin}–{s.yearMax}</td></tr>)}
            {!summary.length && <tr><td colSpan={5} className="text-muted-foreground">None yet.</td></tr>}</tbody>
        </table>
      </section>

      <section className="panel mb-6 space-y-3 p-4">
        <h3 className="text-base">Structured import (India MoSPI · UAE official statistics · manual)</h3>
        <p className="text-xs text-muted-foreground">For education, housing, household expenditure, family formation, migration and pension tables you downloaded from an official source. Required columns: domain, metric, value, unit, country, year, source, source_organization. No PDF or web-page scraping.</p>
        <div className="flex items-end gap-3">
          <Field label="Provider"><select className="input" value={prov} onChange={(e) => setProv(e.target.value as ImportProvider)}><option value="india-mospi">India MoSPI</option><option value="uae-fcsc">UAE FCSC</option><option value="manual">Manual</option></select></Field>
          <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => { const f = e.target.files?.[0]; if (f) void f.text().then(setCsv); }} />
        </div>
        <textarea aria-label="CSV text" className="input h-24 w-full font-mono text-[11px]" placeholder="domain,metric,metric_label,value,unit,country,year,geo_level,region,sex,source,source_organization" value={csv} onChange={(e) => setCsv(e.target.value)} />
        <div className="flex gap-2">
          <button className="btn" disabled={!csv} onClick={() => void run(async () => { setPreview(await api.importPreview(prov, csv)); })}>Preview</button>
          <button className="btn-primary" disabled={!preview || !preview.valid} onClick={() => void run(async () => { const r = await api.importCommit(prov, csv); setPreview(null); return `Imported ${r.committed} row(s).`; })}><Upload className="h-4 w-4" /> Import valid rows</button>
        </div>
        {preview && (
          <div className="text-xs">{preview.errors.map((e) => <div key={e} className="text-fail">{e}</div>)}
            {preview.valid} valid of {preview.rows.length}. {preview.rows.filter((r) => r.errors.length).slice(0, 10).map((r) => <div key={r.line} className="text-fail">Line {r.line}: {r.errors.join("; ")}</div>)}</div>
        )}
      </section>

      <div className="grid grid-cols-2 gap-6">
        <section className="panel">
          <div className="panel-header"><h3 className="text-base">Historical event registry ({events.length})</h3></div>
          <ul className="max-h-96 divide-y divide-border overflow-y-auto text-xs">
            {events.map((e) => (
              <li key={e.id} className="flex gap-2 px-4 py-2">
                <div className="flex-1"><div className="font-medium">{e.name}</div><div className="text-muted-foreground">{e.startDate}{e.endDate ? `–${e.endDate}` : ""} · {e.geography.join(", ")}{e.region ? ` (${e.region})` : ""} · {e.sources.map((s) => s.organization).join("; ")}</div></div>
                <button className="btn-ghost text-xs" onClick={() => void run(async () => { await api.verifyEvent(e.id, e.verification !== "verified"); })}>{e.verification === "verified" ? "✓ verified" : "Mark verified"}</button>
              </li>
            ))}
          </ul>
          <p className="px-4 py-2 text-[10px] text-muted-foreground">Seeded entries are unverified until you check them against the cited organisation.</p>
        </section>
        <section className="panel">
          <div className="panel-header"><h3 className="text-base">Policy evidence ({policies.length})</h3></div>
          <ul className="max-h-96 divide-y divide-border overflow-y-auto text-xs">
            {policies.map((p) => (
              <li key={p.id} className="flex gap-2 px-4 py-2">
                <div className="flex-1"><div className="font-medium">{p.country} · {p.title}</div><div className="text-muted-foreground">{p.policyType} · {p.effectiveStart}–{p.effectiveEnd ?? "in force"} · {p.sourceOrganization}</div><div>{p.description}</div></div>
                <button className="btn-ghost text-xs" onClick={() => void run(async () => { await api.verifyPolicy(p.id, p.verification !== "verified"); })}>{p.verification === "verified" ? "✓ verified" : "Mark verified"}</button>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel col-span-2">
          <div className="panel-header"><h3 className="text-base">Qualitative social context ({context.length})</h3><span className="text-[11px] text-muted-foreground">Context, not statistical fact — every claim needs a source and scope</span></div>
          <div className="grid grid-cols-4 gap-2 p-4">
            <Field label="Topic"><select className="input" value={ctx.topic} onChange={(e) => setCtx({ ...ctx, topic: e.target.value })}>{["family-expectations", "marriage-norms", "education-expectations", "migration-attitudes", "gender-roles", "multi-generational-households", "social-status", "other"].map((t) => <option key={t}>{t}</option>)}</select></Field>
            <Field label="Country"><input className="input" value={ctx.country} onChange={(e) => setCtx({ ...ctx, country: e.target.value.toUpperCase() })} /></Field>
            <Field label="From"><input type="number" className="input" value={ctx.yearStart} onChange={(e) => setCtx({ ...ctx, yearStart: Number(e.target.value) })} /></Field>
            <Field label="To"><input type="number" className="input" value={ctx.yearEnd} onChange={(e) => setCtx({ ...ctx, yearEnd: Number(e.target.value) })} /></Field>
            <div className="col-span-4"><Field label="Claim"><input aria-label="Context claim" className="input w-full" value={ctx.claim} onChange={(e) => setCtx({ ...ctx, claim: e.target.value })} /></Field></div>
            <Field label="Population scope"><input className="input" value={ctx.populationScope} onChange={(e) => setCtx({ ...ctx, populationScope: e.target.value })} /></Field>
            <Field label="Source"><input className="input" value={ctx.source} onChange={(e) => setCtx({ ...ctx, source: e.target.value })} /></Field>
            <Field label="Evidence type"><select className="input" value={ctx.evidenceType} onChange={(e) => setCtx({ ...ctx, evidenceType: e.target.value })}>{["QUALITATIVE", "SURVEY_FINDING", "ETHNOGRAPHIC", "LEGAL_TEXT", "MEASURABLE_CLAIM"].map((t) => <option key={t}>{t}</option>)}</select></Field>
            <div className="flex items-end"><button className="btn" disabled={ctx.claim.length < 10 || ctx.source.length < 3 || ctx.populationScope.length < 3} onClick={() => void run(async () => { await api.createContext(ctx); setCtx({ ...ctx, claim: "" }); })}>Add context record</button></div>
          </div>
          <ul className="divide-y divide-border text-xs">
            {context.map((c) => <li key={c.id} className="flex gap-2 px-4 py-2"><div className="flex-1">{c.claim}<div className="text-muted-foreground">{c.topic} · {c.country} {c.yearStart}–{c.yearEnd} · {c.populationScope} · {c.evidenceType} · {c.source}</div></div><button className="btn-ghost text-xs" onClick={() => void run(async () => { await api.deleteContext(c.id); })}>Delete</button></li>)}
            {!context.length && <li className="px-4 py-3 text-muted-foreground">None recorded. LifeSpan does not invent social norms.</li>}
          </ul>
        </section>
      </div>
    </>
  );
}
