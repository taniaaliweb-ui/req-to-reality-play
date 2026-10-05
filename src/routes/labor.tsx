import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Download, FileUp } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { Field, PageHeader } from "@/components/lifespan/primitives";
import { ApiError, lifespanApi, type ImportProvider } from "@/services/lifespanApi";
import type { ImportPreview, ProviderInfo, SyncReport, WageDistribution, WageObservation } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/labor")({
  head: pageHead("Labor Data", "Official wage and labour-market statistics from ILOSTAT and imported national surveys, stored locally with full provenance."),
  component: LaborData,
});

const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed.");
export const fmtWage = (v: string | null) => (v == null ? "—" : Number(v).toLocaleString("en-US", { maximumFractionDigits: 0 }));
const dims = (w: WageObservation) =>
  [w.sex && w.sex !== "TOTAL" && w.sex, w.occupationLabel && `${w.occupationLabel} (${w.occupationClassification})`, w.educationLabel && `Edu: ${w.educationLabel}`,
    w.industryLabel && `Ind: ${w.industryLabel}`, w.ruralUrban, w.citizenship, w.region, w.ageGroup].filter(Boolean).join(" · ") || "All employees";

const TEMPLATE = "metric,value,unit,currency,country,year,source,source_organization,source_url,statistic_type,pay_period,gross_or_net,occupation,education,region,sex,citizenship,urban_rural,employment_status,survey,bin_lower,bin_upper,count,share,notes";

function LaborData() {
  const { mode } = useLifespan();
  const api = lifespanApi.labor;
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const ilo = providers.find((p) => p.id === "ilostat");
  const [form, setForm] = useState({ countries: "IND, ARE", yearStart: 1990, yearEnd: 2024, flows: ["DF_EAR_EMTA_SEX_OCU_NB", "DF_EAR_EMTM_SEX_NB"] });
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<WageObservation[]>([]);
  const [dists, setDists] = useState<WageDistribution[]>([]);
  const [f, setF] = useState({ country: "", yearStart: "", yearEnd: "", occupation: "", education: "", sex: "", urbanRural: "", industry: "", citizenship: "", provider: "" });
  const [imp, setImp] = useState<{ provider: ImportProvider; csv: string; preview: ImportPreview | null; done: string | null }>({ provider: "manual", csv: "", preview: null, done: null });

  const refresh = useCallback(async () => {
    try {
      const [p, w, d] = await Promise.all([lifespanApi.truth.providers(true), api.wageObservations({ ...f, limit: 1000 }), api.distributions()]);
      setProviders(p);
      setRows(w);
      setDists(d);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [api, f]);
  useEffect(() => {
    if (mode === "backend") void refresh();
  }, [mode, refresh]);

  const fetchData = async () => {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const countries = form.countries.split(/[\s,]+/).map((c) => c.trim().toUpperCase()).filter(Boolean);
      setReport(await api.syncIlostat({ indicators: form.flows, countries, yearStart: form.yearStart, yearEnd: form.yearEnd }));
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };
  const preview = async () => {
    try {
      setImp({ ...imp, preview: await api.importPreview(imp.provider, imp.csv), done: null });
    } catch (e) {
      setError(errMsg(e));
    }
  };
  const commit = async () => {
    try {
      const r = await api.importCommit(imp.provider, imp.csv);
      setImp({ ...imp, preview: null, done: `Imported ${r.imported} row(s). ${r.invalid} invalid and ${r.duplicates} duplicate row(s) were skipped.` });
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    }
  };
  const loadFile = async (file: File | undefined) => file && setImp({ ...imp, csv: await file.text(), preview: null, done: null });

  const sources = useMemo(() => Array.from(new Set(rows.map((r) => r.provider))), [rows]);

  if (mode !== "backend")
    return (
      <>
        <PageHeader eyebrow="Evidence" title="Labor Data" />
        <div className="panel p-6 text-sm text-muted-foreground">Labour statistics are retrieved and stored by the LifeSpan backend only. Start LifeSpan with <code className="data">./scripts/start-local.sh</code>.</div>
      </>
    );

  return (
    <>
      <PageHeader eyebrow="Evidence · Labour" title="Labor Data" description="Published wage statistics describe populations, never a specific character. Missing years stay missing." />

      <div className="mb-6 grid grid-cols-4 gap-3">
        {providers.filter((p) => p.id !== "world-bank").map((p) => (
          <div key={p.id} className="panel p-3 text-xs">
            <div className="flex items-center gap-2"><span className="font-medium text-sm">{p.name}</span></div>
            <div className="mt-1 flex gap-1.5">
              <span className={cn("chip", p.status === "available" ? "border-pass text-pass" : p.status === "import" ? "border-fact text-fact" : p.status === "disabled" ? "border-border text-muted-foreground" : "border-fail text-fail")}>
                {p.status === "import" ? "Manual import" : p.status}
              </span>
              <span className="chip border-border">{p.mode ?? ""}</span>
            </div>
            <div className="mt-2 text-muted-foreground">{p.detail}</div>
            <div className="mt-1 data">{p.storedObservations} stored</div>
          </div>
        ))}
      </div>

      <section className="panel mb-6 p-4">
        <div className="eyebrow mb-3">Fetch from ILOSTAT (official ILO SDMX web service · free, no key)</div>
        <div className="grid grid-cols-[1fr_110px_110px] gap-3">
          <Field label="Countries (ISO3, comma-separated)"><input aria-label="ILO countries" className="input data" value={form.countries} onChange={(e) => setForm({ ...form, countries: e.target.value })} /></Field>
          <Field label="From year"><input aria-label="ILO from year" type="number" className="input data" value={form.yearStart} onChange={(e) => setForm({ ...form, yearStart: Number(e.target.value) })} /></Field>
          <Field label="To year"><input aria-label="ILO to year" type="number" className="input data" value={form.yearEnd} onChange={(e) => setForm({ ...form, yearEnd: Number(e.target.value) })} /></Field>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          {(ilo?.indicators ?? []).map((i) => (
            <label key={i.code} className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.flows.includes(i.code)} onChange={(e) => setForm({ ...form, flows: e.target.checked ? [...form.flows, i.code] : form.flows.filter((x) => x !== i.code) })} />
              <span>{i.name}</span> <span className="chip border-border text-[10px]">{i.kind === "context" ? "context" : i.precisionNote}</span>
            </label>
          ))}
        </div>
        <div className="mt-3 flex items-center">
          <span className="text-xs text-muted-foreground">Labour-market context series are stored for later phases; they do not generate life events.</span>
          <button className="btn-primary ml-auto" disabled={busy || form.flows.length === 0} onClick={() => void fetchData()}><Download className="h-4 w-4" /> {busy ? "Fetching…" : "Fetch data"}</button>
        </div>
        {error && <div className="mt-3 rounded-sm border border-fail/50 bg-fail/5 p-2 text-sm text-fail">{error}</div>}
        {report && (
          <div className="mt-3 rounded-sm border border-border p-3 text-xs">
            <div className="mb-1 font-medium">ILOSTAT · status {report.status} · {report.finishedAt}</div>
            <div>Records retrieved: <b className="data">{report.retrieved}</b> · Country-years with no data: <b className="data">{report.unavailable}</b> (never filled in)</div>
            {report.error && <div className="text-fail">{report.error}</div>}
            <ul className="mt-1 space-y-0.5">
              {report.indicators.map((i) => (
                <li key={i.indicator} className="data">{i.indicator}: {i.retrieved} retrieved{i.created !== undefined && ` (${i.created} new, ${i.unchanged} unchanged, ${i.revised} revised)`}{i.error && <span className="text-fail"> · {i.error}</span>}
                  {i.missing?.length ? <span className="text-muted-foreground"> · e.g. no data {i.missing.slice(0, 5).map((m) => `${m.country} ${m.year}`).join(", ")}</span> : null}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="panel mb-6 p-4">
        <div className="eyebrow mb-2">Import official tables (CSV) — India MoSPI / PLFS, UAE FCSC, or manual</div>
        <p className="mb-3 text-xs text-muted-foreground">No scraping. Download a published table, arrange it in this column layout, and preview before saving. Required: metric, unit, country, year, source, source_organization, plus value (or count/share for wage-group rows).</p>
        <div className="flex items-center gap-3">
          <select aria-label="Import provider" className="input w-56" value={imp.provider} onChange={(e) => setImp({ ...imp, provider: e.target.value as ImportProvider, preview: null })}>
            <option value="manual">Manual / other official source</option>
            <option value="india-mospi">India MoSPI (PLFS)</option>
            <option value="uae-fcsc">UAE FCSC (Labour Force)</option>
          </select>
          <label className="btn cursor-pointer"><FileUp className="h-4 w-4" /> Choose CSV<input aria-label="CSV file" type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => void loadFile(e.target.files?.[0])} /></label>
          <button className="btn-ghost" onClick={() => setImp({ ...imp, csv: TEMPLATE + "\n", preview: null })}>Insert column template</button>
        </div>
        <textarea aria-label="CSV text" className="input data mt-3 h-28 w-full text-[11px]" value={imp.csv} onChange={(e) => setImp({ ...imp, csv: e.target.value, preview: null })} placeholder={TEMPLATE} />
        <div className="mt-2 flex gap-2">
          <button className="btn" disabled={!imp.csv.trim()} onClick={() => void preview()}>Preview</button>
          <button className="btn-primary" disabled={!imp.preview || imp.preview.valid + imp.preview.changed === 0} onClick={() => void commit()}>Save {imp.preview ? imp.preview.valid + imp.preview.changed : ""} row(s)</button>
        </div>
        {imp.done && <div className="mt-2 text-xs text-pass">{imp.done}</div>}
        {imp.preview && (
          <div className="mt-3 text-xs">
            {imp.preview.errors.map((e) => <div key={e} className="text-fail">{e}</div>)}
            <div className="mb-1">Rows detected <b>{imp.preview.rowsDetected}</b> · Valid <b className="text-pass">{imp.preview.valid}</b> · Changed <b className="text-warn">{imp.preview.changed}</b> · Invalid <b className="text-fail">{imp.preview.invalid}</b> · Duplicates <b>{imp.preview.duplicates}</b></div>
            <table className="tbl"><thead><tr><th>Line</th><th>Status</th><th>Metric</th><th>Country</th><th>Year</th><th>Value</th><th>Problems</th></tr></thead>
              <tbody>{imp.preview.rows.slice(0, 50).map((r) => (
                <tr key={r.line}><td className="data">{r.line}</td><td className={cn(r.status === "invalid" && "text-fail", r.status === "valid" && "text-pass", r.status === "changed" && "text-warn")}>{r.status}</td>
                  <td>{r.data["metric"]}</td><td className="data">{r.data["country"]}</td><td className="data">{r.data["year"]}</td><td className="data">{r.data["value"] || r.data["count"] || r.data["share"]}</td><td className="text-muted-foreground">{r.errors.join("; ")}</td></tr>
              ))}</tbody></table>
          </div>
        )}
      </section>

      <section className="panel mb-6">
        <div className="panel-header flex-wrap gap-2">
          <h3 className="text-base">Wage evidence <span className="data text-xs text-muted-foreground">({rows.length})</span></h3>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input aria-label="Filter country" placeholder="Country" className="input w-20 py-1" value={f.country} onChange={(e) => setF({ ...f, country: e.target.value.toUpperCase() })} />
            <input aria-label="Filter from" placeholder="From" className="input w-16 py-1" value={f.yearStart} onChange={(e) => setF({ ...f, yearStart: e.target.value })} />
            <input aria-label="Filter to" placeholder="To" className="input w-16 py-1" value={f.yearEnd} onChange={(e) => setF({ ...f, yearEnd: e.target.value })} />
            <input aria-label="Filter occupation" placeholder="Occupation" className="input w-28 py-1" value={f.occupation} onChange={(e) => setF({ ...f, occupation: e.target.value })} />
            <input aria-label="Filter education" placeholder="Education" className="input w-24 py-1" value={f.education} onChange={(e) => setF({ ...f, education: e.target.value })} />
            <input aria-label="Filter industry" placeholder="Industry" className="input w-24 py-1" value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} />
            <select aria-label="Filter sex" className="input w-24 py-1" value={f.sex} onChange={(e) => setF({ ...f, sex: e.target.value })}><option value="">Any sex</option><option>TOTAL</option><option>MALE</option><option>FEMALE</option></select>
            <select aria-label="Filter area" className="input w-24 py-1" value={f.urbanRural} onChange={(e) => setF({ ...f, urbanRural: e.target.value })}><option value="">Any area</option><option>URBAN</option><option>RURAL</option><option>NATIONAL</option></select>
            <select aria-label="Filter citizenship" className="input w-32 py-1" value={f.citizenship} onChange={(e) => setF({ ...f, citizenship: e.target.value })}><option value="">Any citizenship</option><option>NATIONAL</option><option>NON_NATIONAL</option></select>
            <select aria-label="Filter source" className="input w-28 py-1" value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })}><option value="">All sources</option>{sources.map((s) => <option key={s}>{s}</option>)}</select>
          </div>
        </div>
        <div className="max-h-[480px] overflow-auto">
          <table className="tbl text-xs">
            <thead><tr><th>Source</th><th>Country</th><th>Year</th><th>Statistic</th><th className="text-right">Value</th><th>Population / dimensions</th><th>Gross/net</th><th>Survey</th><th>Retrieved</th></tr></thead>
            <tbody>
              {rows.map((w) => (
                <tr key={w.id}>
                  <td>{w.provider}</td><td className="data">{w.country}</td><td className="data">{w.period}</td>
                  <td>{w.statisticType.toLowerCase()} {w.payPeriod.toLowerCase()}</td>
                  <td className="data text-right" title={w.value ?? ""}>{fmtWage(w.value)} <span className="text-muted-foreground">{w.currency ?? ""}</span></td>
                  <td>{dims(w)}</td><td className="data">{w.grossOrNet}</td><td className="text-muted-foreground">{w.surveyName ?? "—"}</td><td className="data">{w.retrievedAt?.slice(0, 10) ?? "—"}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={9} className="py-8 text-center text-muted-foreground">No wage evidence stored for this filter.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><h3 className="text-base">Wage distributions (wage-group evidence)</h3></div>
        <div className="p-4 text-xs">
          {dists.length === 0 && <div className="text-muted-foreground">No distributions imported. A wage group is evidence of an interval — never an exact salary.</div>}
          {dists.map((d) => (
            <div key={d.id} className="mb-3">
              <div className="font-medium">{d.metric} · {d.country} {d.year} · {Object.values(d.dimensions).join(" · ")} <span className="text-muted-foreground">({d.sourceOrganization})</span></div>
              <table className="tbl mt-1"><thead><tr><th>Wage group ({d.currency})</th><th className="text-right">Count</th><th className="text-right">Share</th></tr></thead>
                <tbody>{d.bins.map((b, i) => (
                  <tr key={i}><td className="data">{b.openLower ? "< " : fmtWage(b.lowerBound) + " – "}{b.openUpper ? "+" : fmtWage(b.upperBound)}</td><td className="data text-right">{b.count ?? "—"}</td><td className="data text-right">{b.share ?? "—"}</td></tr>
                ))}</tbody></table>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
