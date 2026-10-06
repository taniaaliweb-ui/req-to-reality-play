// Canonical-life product panels (story engine, production workspace, Life Receipt 2.0, exports, MCP status, candidate evidence).
import { Download, FileUp, Redo2, RefreshCw, Save, Undo2 } from "lucide-react";
import { useTextHistory } from "@/features/production/history";
import { useEffect, useState } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { BackendOnly, ErrorLine, money, useBackend } from "@/components/lifespan/sim";
import { lifespanApi } from "@/services/lifespanApi";

const sim = lifespanApi.sim;
const TYPE_STYLE: Record<string, string> = {
  FACTUAL_CONTEXT: "text-pass", DERIVED_DATA: "text-primary", SIMULATED_EVENT: "text-sim", ASSUMPTION: "text-warn", NARRATIVE_INTERPRETATION: "italic text-muted-foreground",
};

export function CanonicalStory({ eid }: { eid: string }) {
  const { data, error, refresh } = useBackend(() => sim.story(eid), [eid]);
  const [showClaims, setShowClaims] = useState(false);
  return (
    <BackendOnly>
      <section className="panel mb-6">
        <div className="panel-header"><div><div className="font-serif text-lg">Story Engine — from canonical life</div><div className="text-[11px] uppercase tracking-wide text-sim">{data?.label ?? "Structured local draft (no AI)"}</div></div>
          <div className="flex gap-2"><label className="text-xs"><input type="checkbox" checked={showClaims} onChange={(e) => setShowClaims(e.target.checked)} /> show claim provenance</label><button className="btn-ghost" onClick={() => void sim.story(eid, true).then(() => refresh())}><RefreshCw className="h-4 w-4" /> Rebuild</button></div></div>
        {error ? <div className="p-4"><ErrorLine msg={error} /></div> : !data ? <div className="p-4 text-sm text-muted-foreground">Loading…</div> : (
          <div className="space-y-4 p-4">
            <div className="text-xs">Story audit: {data.audit.length === 0 ? <span className="text-pass">no issues</span> : data.audit.map((a, i) => <div key={i} className={a.severity === "error" ? "text-fail" : "text-warn"}>{a.ruleId}: {a.message}</div>)}</div>
            {data.chapters.map((c) => {
              const claims = data.claims.filter((x) => c.claimIds.includes(x.id));
              return (
                <div key={c.key}>
                  <div className="font-serif text-base">{c.number}. {c.title} <span className="data text-xs text-muted-foreground">{c.yearStart}–{c.yearEnd}</span></div>
                  {c.questions.map((q) => <div key={q} className="text-xs text-primary">? {q}</div>)}
                  {showClaims ? claims.map((x) => <div key={x.id} className={`text-sm ${TYPE_STYLE[x.type] ?? ""}`}><span className="data mr-1 text-[10px]">[{x.type}]</span>{x.text}</div>) : <p className="text-sm leading-6">{c.draft}</p>}
                </div>
              );
            })}
            <details><summary className="cursor-pointer text-sm font-medium">Story beats ({data.beats.length})</summary>
              {data.beats.map((b) => <div key={b.id} className="border-t border-border py-2 text-xs"><b>{b.year} · age {b.age} · {b.chapterTitle}</b><div>Setup: {b.setup}</div>{b.tension && <div>Tension: {b.tension}</div>}{b.decision && <div>Decision: {b.decision}</div>}<div>Consequence: {b.consequence}</div>{b.payoff && <div>Payoff: {b.payoff}</div>}{b.emotionalInterpretation.labels.length > 0 && <div className="italic text-muted-foreground">Narrative interpretation: {b.emotionalInterpretation.labels.join(", ")}</div>}</div>)}
            </details>
          </div>
        )}
      </section>
    </BackendOnly>
  );
}

export function ProductionWorkspace({ eid }: { eid: string }) {
  const { data, error, refresh, setData } = useBackend(() => sim.production(eid), [eid]);
  const hist = useTextHistory(eid, data?.script);
  const script = hist.value;
  const setScript = hist.set;
  const [msg, setMsg] = useState<string | null>(null);
  const words = script.split(/\s+/).filter(Boolean).length;
  return (
    <BackendOnly>
      {error ? <ErrorLine msg={error} /> : !data ? <div className="text-sm text-muted-foreground">Loading production workspace…</div> : (
        <div className="mb-6 space-y-4">
          <div className="panel p-4 text-sm"><div className="font-serif text-lg">Episode Summary</div><p>{data.summary}</p>
            <div className="mt-2 grid grid-cols-1 gap-1 text-xs md:grid-cols-2">{data.outline.map((o) => <div key={o.number}><b>{o.number}. {o.title}</b> <span className="data text-muted-foreground">{o.years.join("–")}</span>{o.questions.map((q) => <div key={q} className="text-primary">? {q}</div>)}</div>)}</div></div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
            <div className="panel">
              <div className="panel-header text-sm"><span>Script editor · {words} words · ~{Math.round((words / 150) * 60 / 60)} min narration {data.edited && "· edited"}</span>
                <div className="flex gap-2"><button className="btn-ghost" onClick={() => void sim.production(eid, true).then((p) => { setData(p); setMsg("Regenerated from the canonical life (manual edits replaced)."); })}><RefreshCw className="h-4 w-4" /> Regenerate</button>
                  <button className="btn-ghost" disabled={!hist.canUndo} title="Undo (Ctrl/Cmd+Z)" onClick={hist.undo}><Undo2 className="h-4 w-4" /> Undo</button>
                  <button className="btn-ghost" disabled={!hist.canRedo} title="Redo (Ctrl/Cmd+Shift+Z)" onClick={hist.redo}><Redo2 className="h-4 w-4" /> Redo</button>
                  <button className="btn-primary" onClick={() => void sim.saveScript(eid, script).then((p) => { setData(p); setMsg("Saved."); }).catch((e: Error) => setMsg(e.message))}><Save className="h-4 w-4" /> Save</button></div></div>
              <div className="flex gap-1 overflow-x-auto border-b border-border p-2 text-xs">{data.check.chapters.map((c) => <button key={c} className="chip" onClick={() => { const i = script.indexOf(`## ${c}`); const ta = document.getElementById("script-ta") as HTMLTextAreaElement | null; if (ta && i >= 0) { ta.focus(); ta.setSelectionRange(i, i); } }}>{c}</button>)}</div>
              <textarea id="script-ta" className="h-[480px] w-full resize-y bg-card p-3 font-mono text-xs leading-5 outline-none" value={script} onChange={(e) => setScript(e.target.value)}
                onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) hist.redo(); else hist.undo(); } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") { e.preventDefault(); hist.redo(); } }} />
              <div className="border-t border-border p-2 text-xs">{msg && <div className="text-pass">{msg}</div>}{data.check.warnings.length === 0 ? <span className="text-pass">No fact warnings.</span> : data.check.warnings.map((w, i) => <div key={i} className="text-warn">⚠ {w.ruleId}: {w.message}</div>)}</div>
            </div>
            <div className="panel max-h-[620px] overflow-auto">
              <div className="panel-header text-sm">Scenes ({data.scenes.length})</div>
              {data.scenes.map((s) => <div key={s.sceneNumber} className="border-t border-border p-2 text-xs"><b>#{s.sceneNumber} · {s.chapter}</b> <span className="data text-muted-foreground">{s.year ?? ""} · {s.location} · {s.estimatedDuration}s</span><div className="text-muted-foreground">Visual: {s.visualConcept}</div><div className="mt-1 flex flex-wrap gap-1">{s.labels.map((l) => <span key={l} className="chip text-[9px]">{l}</span>)}</div><div className="data mt-1 truncate text-[10px] text-muted-foreground">sources: {s.sourceIds.join(", ")}</div></div>)}
            </div>
          </div>
          <div className="panel p-4 text-xs"><div className="mb-1 text-sm font-medium">Narration notes</div>{data.narrationNotes.map((n) => <div key={n}>• {n}</div>)}</div>
          <button className="btn-ghost hidden" onClick={() => void refresh()} />
        </div>
      )}
    </BackendOnly>
  );
}

export function Receipt2Panel({ eid }: { eid: string }) {
  const { data, error } = useBackend(() => sim.receipt(eid), [eid]);
  const { data: app } = useBackend(() => sim.appendix(eid), [eid]);
  if (lifespanApi.mode !== "backend") return null;
  if (error) return <ErrorLine msg={error} />;
  if (!data) return null;
  const fmt = (v: unknown): string => (v && typeof v === "object" && !Array.isArray(v) ? (Object.values(v as object).every((x) => typeof x === "string") ? money(v as Record<string, string>) : JSON.stringify(v)) : Array.isArray(v) ? v.join("; ") || "—" : String(v ?? "—"));
  return (
    <section className="panel mb-6">
      <div className="panel-header"><div className="font-serif text-lg">Life Receipt 2.0 — canonical life</div><span className="text-[11px] uppercase text-sim">{data.label}</span></div>
      <table className="w-full text-sm"><tbody>{Object.entries(data).filter(([k]) => !["label", "provenance"].includes(k)).map(([k, v]) => <tr key={k} className="border-t border-border align-top"><td className="w-56 p-2 text-muted-foreground">{k.replace(/([A-Z])/g, " $1")}</td><td className="data p-2 text-xs">{fmt(v)}</td></tr>)}</tbody></table>
      <div className="border-t border-border p-3 text-xs"><div className="field-label">Provenance</div>{Object.entries(data.provenance).filter(([k]) => !k.endsWith("Ids")).map(([k, v]) => <div key={k}>{k}: <span className="data">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span></div>)}</div>
      {app && <details className="border-t border-border p-3 text-xs"><summary className="cursor-pointer font-medium">Source appendix</summary>{Object.entries(app).map(([k, v]) => <div key={k} className="mt-2"><div className="field-label">{k} ({v.length})</div>{v.slice(0, 40).map((x, i) => <div key={i} className="data truncate">{Object.values(x).filter(Boolean).join(" · ")}</div>)}</div>)}</details>}
    </section>
  );
}

export function ExportPanel({ eid }: { eid: string }) {
  const { reload, setActiveId } = useLifespan();
  const [msg, setMsg] = useState<string | null>(null);
  if (lifespanApi.mode !== "backend") return null;
  const download = async () => {
    const a = await sim.exportArchive(eid);
    const url = URL.createObjectURL(new Blob([JSON.stringify(a, null, 1)], { type: "application/json" }));
    const el = document.createElement("a");
    el.href = url;
    el.download = `lifespan-${eid}.archive.json`;
    el.click();
    URL.revokeObjectURL(url);
  };
  const upload = async (f: File) => {
    try {
      const r = await sim.importArchive(JSON.parse(await f.text()));
      await reload();
      setActiveId(r.episodeId);
      setMsg(`Imported as new episode ${r.episodeId}. ${r.note}`);
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <section className="panel mb-6 p-4 text-sm">
      <div className="mb-2 font-medium">Export (local, free)</div>
      <div className="flex flex-wrap gap-2">
        <button className="btn-ghost" onClick={() => void download()}><Download className="h-4 w-4" /> Full episode archive (JSON)</button>
        <a className="btn-ghost" href={sim.exportUrl(eid, "ledger.csv")} target="_blank" rel="noreferrer">Economic ledger (CSV)</a>
        <a className="btn-ghost" href={sim.exportUrl(eid, "story.md")} target="_blank" rel="noreferrer">Story + receipt (Markdown)</a>
        <a className="btn-ghost" href={sim.exportUrl(eid, "printable.html")} target="_blank" rel="noreferrer">Printable HTML → Print / Save as PDF</a>
        <label className="btn-ghost cursor-pointer"><FileUp className="h-4 w-4" /> Import archive as new episode<input type="file" accept="application/json" className="hidden" onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])} /></label>
      </div>
      {msg && <div className="mt-2 text-xs">{msg}</div>}
    </section>
  );
}

export function McpStatusPanel() {
  const { data, error, loading, refresh } = useBackend(() => sim.mcpStatus(), []);
  const { data: orch } = useBackend(() => sim.orchestration(), []);
  if (lifespanApi.mode !== "backend") return null;
  return (
    <section className="panel mt-6 p-4 text-sm">
      <div className="flex items-center gap-2"><span className="font-medium">Local MCP server</span><span className={`chip ${data?.status === "AVAILABLE" ? "text-pass" : "text-fail"}`}>{loading ? "TESTING…" : data?.status ?? (error ? "ERROR" : "DISABLED")}</span><button className="btn-ghost ml-auto" onClick={() => void refresh()}>Re-test</button></div>
      <div className="mt-1 text-xs text-muted-foreground">{data?.detail ?? error} {data?.command && <>Start: <code className="data">cd backend && {data.command}</code></>}</div>
      {data?.tools && <div className="data mt-1 text-[11px]">{data.tools.join(" · ")}</div>}
      <div className="mt-1 text-xs">{data?.aiIntegrations}</div>
      {orch && <div className="mt-3 text-xs"><span className="font-medium">AI orchestration:</span> {orch.active ? "active" : "prepared, not active"} · default provider {orch.defaultProvider} · {orch.providers.map((p) => `${p.provider} ${p.status}`).join(", ")}</div>}
    </section>
  );
}

export function CandidateEvidencePanel({ eid }: { eid: string }) {
  const { data, refresh } = useBackend(() => sim.candidates(eid), [eid]);
  const [f, setF] = useState({ claim: "", value: "", unit: "", source: "", url: "" });
  if (lifespanApi.mode !== "backend") return null;
  return (
    <section className="panel mt-6">
      <div className="panel-header text-sm"><span>Candidate evidence (submitted research awaiting human review)</span></div>
      <div className="grid grid-cols-2 gap-2 p-3 md:grid-cols-6">
        {(["claim", "value", "unit", "source", "url"] as const).map((k) => <input key={k} className="input text-xs" placeholder={k} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />)}
        <button className="btn-primary" disabled={f.claim.length < 3 || f.source.length < 2} onClick={() => void sim.submitCandidate({ ...f, episodeId: eid }).then(() => { setF({ claim: "", value: "", unit: "", source: "", url: "" }); void refresh(); })}>Submit</button>
      </div>
      {(data ?? []).map((c) => (
        <div key={c.id} className="flex items-center gap-2 border-t border-border px-3 py-2 text-xs">
          <span className="data">{c.id}</span><span className="flex-1">{c.claim} {c.value && `= ${c.value} ${c.unit}`} <span className="text-muted-foreground">({c.source}, by {c.submittedBy})</span></span><span className="chip">{c.status}</span>
          {c.status === "PENDING_REVIEW" && <><button className="btn-ghost" onClick={() => void sim.reviewCandidate(c.id, "ACCEPTED").then(() => refresh())}>Accept</button><button className="btn-ghost" onClick={() => void sim.reviewCandidate(c.id, "REJECTED").then(() => refresh())}>Reject</button></>}
        </div>
      ))}
    </section>
  );
}
