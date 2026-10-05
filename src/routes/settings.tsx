import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { Field, PageHeader } from "@/components/lifespan/primitives";
import type { AppSettings, LifespanDB } from "@/types/lifespan";
import { API_URL, lifespanApi, readLocalWorkspace, type ImportReport } from "@/services/lifespanApi";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/settings")({
  head: pageHead("Settings", "Data mode, endpoints, display preferences and local data import."),
  component: Settings,
});

function Settings() {
  const { db, mutate, reset, mode, reload } = useLifespan();
  const s = db.settings;
  const set = (p: Partial<AppSettings>) => mutate((d) => ({ ...d, settings: { ...d.settings, ...p } }));
  const [localData, setLocalData] = useState<LifespanDB | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setLocalData(readLocalWorkspace()), []);

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(db, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "lifespan-export.json";
    a.click();
  };

  const doImport = async () => {
    if (!localData) return;
    setBusy(true);
    setReport(null);
    try {
      let r: ImportReport = await lifespanApi.importWorkspace(localData, false);
      if (r.conflicts.length > 0 && confirm(`${r.conflicts.length} record(s) already exist in the backend and were skipped.\n\nOverwrite them with your browser copies?`)) {
        r = await lifespanApi.importWorkspace(localData, true);
      }
      setReport(`Import finished: ${r.created} created, ${r.updated} updated, ${r.skipped} skipped. Browser data was left untouched.`);
      await reload();
    } catch (e) {
      setReport(`Import failed: ${e instanceof Error ? e.message : "unknown error"}. Nothing in your browser was changed.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader eyebrow="System" title="Settings" />
      <div className="grid max-w-3xl gap-6">
        <section className="panel space-y-2 p-5 text-sm">
          <div className="eyebrow">Data mode</div>
          <div>
            Current: <span className="data font-semibold">{mode}</span>{" "}
            {mode === "backend" ? <>— canonical data in local SQLite via <code className="data">{API_URL}</code></> : "— browser storage prototype (not shared, not canonical)"}
          </div>
          <p className="text-xs text-muted-foreground">Set with <code className="data">VITE_LIFESPAN_DATA_MODE</code> when starting the app. The Mac launcher uses backend mode.</p>
        </section>

        {mode === "backend" && localData && (
          <section className="panel space-y-3 p-5">
            <div className="eyebrow">Import Local Prototype Data</div>
            <p className="text-sm">This browser has Phase 1 data: {localData.episodes.length} episode(s), {localData.facts.length} facts, {localData.timeline.length} events.</p>
            <p className="text-xs text-muted-foreground">Records are validated by the backend and IDs preserved. Existing backend records are only overwritten if you confirm. Browser data is never deleted.</p>
            <button className="btn-primary" disabled={busy} onClick={doImport}>{busy ? "Importing…" : "Import Local Prototype Data"}</button>
            {report && <div className="rounded-sm border border-border bg-secondary px-3 py-2 text-xs">{report}</div>}
          </section>
        )}

        <section className="panel space-y-4 p-5">
          <div className="eyebrow">Future endpoints</div>
          <Field label="Hermes URL (not called yet)"><input className="input data" value={s.hermesUrl} onChange={(e) => set({ hermesUrl: e.target.value })} /></Field>
          <p className="text-xs text-muted-foreground">API keys are never stored in the browser. They will live in the backend's environment.</p>
        </section>
        <section className="panel space-y-3 p-5">
          <div className="eyebrow">External data (backend only)</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.externalDataEnabled ?? true} onChange={(e) => set({ externalDataEnabled: e.target.checked })} /> External data access enabled</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.worldBankEnabled ?? true} onChange={(e) => set({ worldBankEnabled: e.target.checked })} /> World Bank provider enabled <span className="text-xs text-muted-foreground">(no API key needed)</span></label>
          <p className="text-xs text-muted-foreground">Future provider credentials will live in the backend environment, never in the browser.</p>
        </section>
        <section className="panel space-y-3 p-5">
          <div className="eyebrow">Display</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.showMockBanners} onChange={(e) => set({ showMockBanners: e.target.checked })} /> Show prototype-data banners</label>
          <Field label="Currency display"><select className="input w-40" value={s.currencyDisplay} onChange={(e) => set({ currencyDisplay: e.target.value as AppSettings["currencyDisplay"] })}><option value="local">Local currency</option><option value="USD">USD (not implemented)</option></select></Field>
        </section>
        <section className="panel flex gap-3 p-5">
          <button className="btn" onClick={exportJson}>Export workspace JSON</button>
          {mode === "local" && <button className="btn" onClick={() => confirm("Reset all browser data to the demo episode?") && reset()}>Reset to demo data</button>}
        </section>
      </div>
    </>
  );
}
