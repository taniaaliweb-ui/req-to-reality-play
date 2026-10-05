import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { Lock, Plus } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, Field, PageHeader } from "@/components/lifespan/primitives";
import { ApiError, lifespanApi } from "@/services/lifespanApi";
import type { DatasetSnapshot, SnapshotDiff, SnapshotManifest } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/snapshots")({
  head: pageHead("Dataset Snapshots", "Freeze the exact facts, observations and baselines an episode uses. Finalized snapshots are immutable and versioned."),
  component: Snapshots,
});

const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Request failed.");

function Snapshots() {
  const { active, mode } = useLifespan();
  const api = lifespanApi.labor;
  const [list, setList] = useState<DatasetSnapshot[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cmp, setCmp] = useState<{ a: string; b: string }>({ a: "", b: "" });
  const [diff, setDiff] = useState<SnapshotDiff | null>(null);
  const [manifest, setManifest] = useState<SnapshotManifest | null>(null);
  const eid = active?.id;

  const refresh = useCallback(async () => {
    if (!eid) return;
    try {
      setList(await api.snapshots(eid));
    } catch (e) {
      setError(errMsg(e));
    }
  }, [api, eid]);
  useEffect(() => {
    if (mode === "backend") void refresh();
  }, [mode, refresh]);
  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  if (mode !== "backend") return (<><PageHeader eyebrow="Evidence" title="Dataset Snapshots" /><div className="panel p-6 text-sm text-muted-foreground">Requires the LifeSpan backend.</div></>);
  if (!active || !eid) return <EmptyEpisode />;

  return (
    <>
      <PageHeader eyebrow="Evidence · Reproducibility" title="Dataset Snapshots" description="Future simulations will run on a pinned snapshot, never on live, changing data. Prototype demo figures are excluded." />
      {error && <div className="mb-4 rounded-sm border border-fail/50 bg-fail/5 p-2 text-sm text-fail">{error}</div>}
      <section className="panel mb-6 flex items-end gap-3 p-4">
        <Field label="Snapshot name"><input aria-label="Snapshot name" className="input w-80" placeholder="Delhi-Dubai Baseline" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <button className="btn-primary" disabled={!name.trim()} onClick={() => void run(() => api.createSnapshot(eid, name.trim()).then(() => setName("")))}><Plus className="h-4 w-4" /> Create dataset snapshot</button>
      </section>

      <section className="panel mb-6">
        <table className="tbl text-xs">
          <thead><tr><th>Snapshot</th><th>Status</th><th>Contains</th><th>Created</th><th>Integrity</th><th></th></tr></thead>
          <tbody>
            {list.map((s) => (
              <tr key={s.id}>
                <td className="font-medium">{s.name}<div className="data text-[10px] text-muted-foreground">{s.id}{s.parentId && ` ← ${s.parentId}`}</div></td>
                <td>{s.status === "final" ? <span className="chip border-pass text-pass"><Lock className="h-3 w-3" /> IMMUTABLE</span> : <span className="chip border-warn text-warn">draft</span>}</td>
                <td>{s.counts.verifiedFacts} verified facts · {s.counts.derived} derived · {s.counts.assumptions} assumptions · {s.counts.observations} observations ({Object.entries(s.counts.observationsByProvider).map(([k, v]) => `${v} ${k}`).join(", ") || "none"}) · {s.counts.baselines} baselines ({s.counts.approvedBaselines} approved)</td>
                <td className="data">{s.createdAt.slice(0, 19)}{s.finalizedAt && <div>final {s.finalizedAt.slice(0, 19)}</div>}</td>
                <td>{s.status !== "final" ? "—" : s.intact === null ? "legacy (unhashed)" : s.intact ? <span className="text-pass">hash verified</span> : <span className="text-fail">MODIFIED</span>}</td>
                <td className="whitespace-nowrap">
                  <button className="btn-ghost text-xs" onClick={() => void run(async () => setManifest(await lifespanApi.life.snapshotManifest(s.id)))}>Manifest</button>
                  {s.status === "draft" ? (
                    <>
                      <button className="btn-ghost text-xs" onClick={() => void run(() => api.refreshSnapshot(s.id))}>Re-collect</button>
                      <button className="btn text-xs" onClick={() => void run(() => api.finalizeSnapshot(s.id))}>Finalize</button>
                      <button className="btn-ghost text-xs" onClick={() => void run(() => api.deleteSnapshot(s.id))}>Delete</button>
                    </>
                  ) : (
                    <button className="btn-ghost text-xs" onClick={() => void run(() => api.newSnapshotVersion(s.id))}>New version</button>
                  )}
                </td>
              </tr>
            ))}
            {list.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-muted-foreground">No snapshots yet.</td></tr>}
          </tbody>
        </table>
      </section>

      {manifest && (
        <section className="panel mb-6 p-4">
          <div className="mb-2 flex items-center gap-2"><h3 className="text-base">Manifest · {manifest.title}</h3>{manifest.status === "final" ? <span className="chip border-pass text-pass"><Lock className="h-3 w-3" /> IMMUTABLE</span> : <span className="chip border-warn text-warn">draft</span>}
            <button className="btn-ghost ml-auto text-xs" onClick={() => setManifest(null)}>Close</button></div>
          <div className="grid grid-cols-3 gap-x-6 gap-y-0.5 text-xs">{manifest.lines.map((l) => <div key={l.label} className="flex justify-between border-b border-border py-0.5"><span>{l.label}</span><span className="data">{l.count}</span></div>)}</div>
          {manifest.readiness && <p className="mt-2 text-xs">Readiness at snapshot time: <span className="font-semibold">{manifest.readiness.overall.replace("_", " ")}</span> — {manifest.readiness.groups.map((g) => `${g.label.replace(" readiness", "")}: ${g.status.replace("_", " ")}`).join(" · ")}</p>}
          {!manifest.phase5Contents && <p className="mt-2 text-xs text-muted-foreground">Created before Phase 5 — contains no life-context records.</p>}
          {manifest.contentHash && <p className="data mt-1 text-[10px] text-muted-foreground">sha256 {manifest.contentHash}</p>}
        </section>
      )}

      <section className="panel">
        <div className="panel-header gap-2">
          <h3 className="text-base">Compare snapshots</h3>
          <div className="flex gap-2">
            <select aria-label="Compare from" className="input w-56 py-1" value={cmp.a} onChange={(e) => setCmp({ ...cmp, a: e.target.value })}><option value="">From…</option>{list.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
            <select aria-label="Compare to" className="input w-56 py-1" value={cmp.b} onChange={(e) => setCmp({ ...cmp, b: e.target.value })}><option value="">To…</option>{list.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
            <button className="btn" disabled={!cmp.a || !cmp.b} onClick={() => void run(async () => setDiff(await api.diffSnapshots(cmp.a, cmp.b)))}>Compare</button>
          </div>
        </div>
        {diff && (
          <div className="grid grid-cols-3 gap-4 p-4 text-xs">
            {(["baselines", "observations", "facts"] as const).map((k) => (
              <div key={k}>
                <div className="eyebrow mb-1">{k} · {diff.from.name} → {diff.to.name}</div>
                {diff[k].filter((x) => x.kind !== "unchanged").map((x) => (
                  <div key={x.id} className={cn(x.kind === "added" && "text-pass", x.kind === "removed" && "text-fail", x.kind === "changed" && "text-warn")}>{x.kind}: {x.label} {x.old !== undefined && x.new !== undefined ? `${x.old} → ${x.new}` : x.new ?? x.old}</div>
                ))}
                <div className="text-muted-foreground">{diff[k].filter((x) => x.kind === "unchanged").length} unchanged</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
