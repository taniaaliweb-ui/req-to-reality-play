import { createFileRoute } from "@tanstack/react-router";
import { useLifespan } from "@/hooks/useLifespan";
import { Field, PageHeader } from "@/components/lifespan/primitives";
import type { AppSettings } from "@/types/lifespan";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/settings")({
  head: pageHead("Settings", "Local endpoints, display preferences and prototype data controls."),
  component: Settings,
});

function Settings() {
  const { db, mutate, reset } = useLifespan();
  const s = db.settings;
  const set = (p: Partial<AppSettings>) => mutate((d) => ({ ...d, settings: { ...d.settings, ...p } }));
  const exportJson = () => {
    const blob = new Blob([JSON.stringify(db, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "lifespan-export.json";
    a.click();
  };
  return (
    <>
      <PageHeader eyebrow="System" title="Settings" />
      <div className="grid max-w-3xl gap-6">
        <section className="panel space-y-4 p-5">
          <div className="eyebrow">Future endpoints (not called in Phase 1)</div>
          <Field label="LifeSpan backend URL"><input className="input data" value={s.backendUrl} onChange={(e) => set({ backendUrl: e.target.value })} /></Field>
          <Field label="Hermes URL"><input className="input data" value={s.hermesUrl} onChange={(e) => set({ hermesUrl: e.target.value })} /></Field>
          <p className="text-xs text-muted-foreground">API keys are never stored in the browser. They will live in the backend's environment.</p>
        </section>
        <section className="panel space-y-3 p-5">
          <div className="eyebrow">Display</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={s.showMockBanners} onChange={(e) => set({ showMockBanners: e.target.checked })} /> Show prototype-data banners</label>
          <Field label="Currency display"><select className="input w-40" value={s.currencyDisplay} onChange={(e) => set({ currencyDisplay: e.target.value as AppSettings["currencyDisplay"] })}><option value="local">Local currency</option><option value="USD">USD (not implemented)</option></select></Field>
        </section>
        <section className="panel flex gap-3 p-5">
          <button className="btn" onClick={exportJson}>Export workspace JSON</button>
          <button className="btn" onClick={() => confirm("Reset all local data to the demo episode?") && reset()}>Reset to demo data</button>
        </section>
      </div>
    </>
  );
}
