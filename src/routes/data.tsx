import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Database, Download, Plus } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { Field, PageHeader } from "@/components/lifespan/primitives";
import { ApiError, lifespanApi } from "@/services/lifespanApi";
import type { ExternalObservation, ProviderInfo, SyncReport } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/data")({
  head: pageHead("Data Sources", "Retrieve authoritative CPI and exchange-rate data into the local truth store."),
  component: DataSources,
});

const SERIES = [
  { code: "FP.CPI.TOTL", label: "Consumer price index" },
  { code: "FP.CPI.TOTL.ZG", label: "Inflation, annual %" },
  { code: "PA.NUS.FCRF", label: "Official exchange rate (annual average)" },
];
const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed.");

function DataSources() {
  const { active, mode, reload } = useLifespan();
  const api = lifespanApi.truth;
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [obs, setObs] = useState<ExternalObservation[]>([]);
  const [form, setForm] = useState({ countries: "IND, ARE", yearStart: 1970, yearEnd: 2025, series: ["FP.CPI.TOTL", "PA.NUS.FCRF"] });
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<SyncReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState({ country: "", indicator: "" });
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [p, o] = await Promise.all([api.providers(true), api.observations()]);
      setProviders(p);
      setObs(o);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [api]);
  useEffect(() => {
    if (mode === "backend") void refresh();
  }, [mode, refresh]);

  const fetchData = async () => {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const countries = form.countries.split(/[\s,]+/).map((c) => c.trim().toUpperCase()).filter(Boolean);
      setReport(await api.syncWorldBank({ indicators: form.series, countries, yearStart: form.yearStart, yearEnd: form.yearEnd }));
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const rows = useMemo(() => obs.filter((o) => (!filter.country || o.countryCode === filter.country) && (!filter.indicator || o.indicatorCode === filter.indicator)), [obs, filter]);
  const countries = Array.from(new Set(obs.map((o) => o.countryCode)));

  const addToLedger = async () => {
    if (!active) return;
    try {
      const r = await api.factsFromObservations(active.id, [...sel]);
      await reload();
      setNotice(`${r.factIds.length} verified FACT record(s) are now in the Fact Ledger of “${active.title}”.`);
      setSel(new Set());
    } catch (e) {
      setError(errMsg(e));
    }
  };
  const pin = async () => {
    if (!active) return;
    try {
      const s = await api.pinSnapshot(active.id, `Snapshot ${new Date().toISOString().slice(0, 10)}`);
      setNotice(`Pinned dataset snapshot ${s.id} with ${s.items.length} observation value(s) used by this episode.`);
    } catch (e) {
      setError(errMsg(e));
    }
  };

  if (mode !== "backend")
    return (
      <>
        <PageHeader eyebrow="System" title="Data Sources" />
        <div className="panel p-6 text-sm text-muted-foreground">External data is retrieved by the LifeSpan backend only. Start LifeSpan with <code className="data">./scripts/start-local.sh</code> to use it.</div>
      </>
    );

  return (
    <>
      <PageHeader eyebrow="System · Truth engine" title="Data Sources" description="Authoritative statistics are retrieved by the backend, stored locally in SQLite, and stay available offline." />

      <div className="mb-6 grid grid-cols-2 gap-4">
        {(providers ?? []).filter((p) => p.id === "world-bank" || p.id === "manual").map((p) => (
          <div key={p.id} className="panel p-4 text-sm">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4" />
              <span className="font-medium">{p.name}</span>
              <span className={cn("chip ml-auto", p.status === "available" ? "border-pass text-pass" : p.status === "disabled" ? "border-border text-muted-foreground" : "border-fail text-fail")}>{p.status}</span>
            </div>
            <div className="mt-2 grid grid-cols-[110px_1fr] gap-y-1 text-xs">
              <span className="text-muted-foreground">Dataset</span><span>{p.dataset}</span>
              <span className="text-muted-foreground">Authentication</span><span>{p.authentication}</span>
              <span className="text-muted-foreground">Stored values</span><span className="data">{p.storedObservations}</span>
              <span className="text-muted-foreground">Last sync</span><span className="data">{p.lastSync ? `${p.lastSync.at} · ${p.lastSync.status}` : "never"}</span>
              {p.indicators.length > 0 && <><span className="text-muted-foreground">Indicators</span><span>{p.indicators.map((i) => i.code).join(", ")}</span></>}
            </div>
          </div>
        ))}
        {!providers && !error && <div className="panel p-4 text-sm text-muted-foreground">Checking providers…</div>}
      </div>

      <section className="panel mb-6 p-4">
        <div className="eyebrow mb-3">Fetch from World Bank (World Development Indicators)</div>
        <div className="grid grid-cols-[1fr_110px_110px] gap-3">
          <Field label="Countries (ISO codes, comma-separated)"><input aria-label="Countries" className="input data" value={form.countries} onChange={(e) => setForm({ ...form, countries: e.target.value })} /></Field>
          <Field label="From year"><input aria-label="From year" type="number" className="input data" value={form.yearStart} onChange={(e) => setForm({ ...form, yearStart: Number(e.target.value) })} /></Field>
          <Field label="To year"><input aria-label="To year" type="number" className="input data" value={form.yearEnd} onChange={(e) => setForm({ ...form, yearEnd: Number(e.target.value) })} /></Field>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          {SERIES.map((s) => (
            <label key={s.code} className="flex items-center gap-1.5">
              <input type="checkbox" checked={form.series.includes(s.code)} onChange={(e) => setForm({ ...form, series: e.target.checked ? [...form.series, s.code] : form.series.filter((x) => x !== s.code) })} />
              {s.label} <span className="data text-[11px] text-muted-foreground">{s.code}</span>
            </label>
          ))}
          <button className="btn-primary ml-auto" disabled={busy || form.series.length === 0} onClick={() => void fetchData()}><Download className="h-4 w-4" /> {busy ? "Fetching…" : "Fetch data"}</button>
        </div>
        {error && <div className="mt-3 rounded-sm border border-fail/50 bg-fail/5 p-2 text-sm text-fail">{error}</div>}
        {report && (
          <div className="mt-3 rounded-sm border border-border p-3 text-xs">
            <div className="mb-1 font-medium">Provider: World Bank · status {report.status} · {report.finishedAt}</div>
            <div>Records retrieved: <b className="data">{report.retrieved}</b> · Records unavailable: <b className="data">{report.unavailable}</b> (never filled in)</div>
            {report.error && <div className="text-fail">{report.error}</div>}
            <ul className="mt-1 space-y-0.5">
              {report.indicators.map((i) => (
                <li key={i.indicator} className="data">
                  {i.indicator}: {i.retrieved} retrieved, {i.unavailable ?? "?"} unavailable{i.created !== undefined && ` · ${i.created} new, ${i.unchanged} unchanged, ${i.revised} revised`}
                  {i.unknownCountries?.length ? ` · unknown: ${i.unknownCountries.join(", ")}` : ""}
                  {i.missing?.length ? <span className="text-muted-foreground"> · missing e.g. {i.missing.slice(0, 4).map((m) => `${m.country} ${m.year}`).join(", ")}</span> : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3 className="text-base">Stored observations <span className="data text-xs text-muted-foreground">({rows.length})</span></h3>
          <div className="flex items-center gap-2">
            <select aria-label="Filter country" className="input w-28 py-1" value={filter.country} onChange={(e) => setFilter({ ...filter, country: e.target.value })}><option value="">All</option>{countries.map((c) => <option key={c}>{c}</option>)}</select>
            <select aria-label="Filter indicator" className="input w-40 py-1" value={filter.indicator} onChange={(e) => setFilter({ ...filter, indicator: e.target.value })}><option value="">All series</option>{SERIES.map((s) => <option key={s.code} value={s.code}>{s.code}</option>)}</select>
            <button className="btn" disabled={!active || sel.size === 0} onClick={() => void addToLedger()}><Plus className="h-3.5 w-3.5" /> Add {sel.size || ""} to Fact Ledger</button>
            <button className="btn-ghost" disabled={!active} onClick={() => void pin()}>Pin snapshot (final)</button>
          </div>
        </div>
        {notice && <div className="border-b border-border bg-pass/5 px-4 py-2 text-xs text-pass">{notice}</div>}
        <div className="max-h-[520px] overflow-auto">
          <table className="tbl text-xs">
            <thead><tr><th><input type="checkbox" aria-label="Select all" checked={rows.length > 0 && rows.every((r) => sel.has(r.id))} onChange={(e) => setSel(e.target.checked ? new Set(rows.map((r) => r.id)) : new Set())} /></th><th>Series</th><th>Country</th><th>Year</th><th className="text-right">Value</th><th>Unit</th><th>Provider updated</th><th>Retrieved (cached)</th></tr></thead>
            <tbody>
              {rows.map((o) => (
                <tr key={o.id}>
                  <td><input type="checkbox" aria-label={`Select ${o.id}`} checked={sel.has(o.id)} onChange={(e) => { const n = new Set(sel); if (e.target.checked) n.add(o.id); else n.delete(o.id); setSel(n); }} /></td>
                  <td className="data">{o.indicatorCode}</td>
                  <td>{o.countryName} <span className="data text-muted-foreground">{o.countryCode}</span></td>
                  <td className="data">{o.year}</td>
                  <td className="data text-right">{o.value}</td>
                  <td className="text-muted-foreground">{o.unit}</td>
                  <td className="data">{o.providerLastUpdated || "—"}</td>
                  <td className="data">{o.retrievedAt}{o.revisions > 0 && <span className="ml-1 text-warn">· revised ×{o.revisions}</span>}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-muted-foreground">No observations stored yet. Use “Fetch data” above.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
