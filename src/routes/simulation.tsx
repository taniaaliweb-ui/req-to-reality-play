import { createFileRoute } from "@tanstack/react-router";
import { Play } from "lucide-react";
import { useState } from "react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, MockBanner, PageHeader, Slider } from "@/components/lifespan/primitives";
import { CONTROL_LABELS } from "@/lib/defaults";
import { normalizeBranches } from "@/features/simulation/engine";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/simulation")({
  head: pageHead("Simulation", "Simulation control center and life-branch decision points."),
  component: Simulation,
});

const EXTRA = { careerVolatility: "Career volatility", relationshipVolatility: "Relationship volatility", healthIntensity: "Health-event intensity" } as const;

function Simulation() {
  const { active, mutate } = useLifespan();
  const { simulation } = useActiveRecords();
  const [msg, setMsg] = useState("");
  if (!active) return <EmptyEpisode />;
  if (!simulation) {
    return (
      <>
        <PageHeader eyebrow="Pipeline · 7" title="Simulation" />
        <div className="panel p-8 text-center text-sm text-muted-foreground">No simulation run exists for this episode. The engine is not implemented in Phase 1, so no branches have been generated.</div>
      </>
    );
  }
  const setCtl = (k: string, v: number) => mutate((d) => ({ ...d, simulations: d.simulations.map((s) => (s.id === simulation.id ? { ...s, controls: { ...s.controls, [k]: v } } : s)) }));
  const choose = (dp: string, b: string) => mutate((d) => ({ ...d, simulations: d.simulations.map((s) => (s.id === simulation.id ? { ...s, decisionPoints: s.decisionPoints.map((p) => (p.id === dp ? { ...p, branches: p.branches.map((x) => ({ ...x, chosen: x.id === b })) } : p)) } : s)) }));

  return (
    <>
      <PageHeader eyebrow="Pipeline · 7" title="Simulation Engine" description="Controls and decision points for the future probabilistic engine." actions={<button className="btn-primary" onClick={() => setMsg("The simulation engine is not implemented yet. Controls are saved and will be used by the deterministic Python engine in a later phase.")}><Play className="h-4 w-4" /> Run simulation</button>} />
      <MockBanner>Prototype Simulation Data — probabilities below are hand-entered examples, not research or engine output.</MockBanner>
      {msg && <div className="mb-4 rounded-sm border border-warn/50 bg-assumption-soft px-3 py-2 text-xs">{msg}</div>}
      <div className="grid grid-cols-[320px_1fr] gap-6">
        <aside className="panel h-fit space-y-4 p-4">
          <label className="block"><span className="field-label">Simulation seed</span>
            <input type="number" className="input data" value={simulation.seed} onChange={(e) => mutate((d) => ({ ...d, simulations: d.simulations.map((s) => (s.id === simulation.id ? { ...s, seed: Number(e.target.value) } : s)) }))} />
          </label>
          {(Object.keys(CONTROL_LABELS) as (keyof typeof CONTROL_LABELS)[]).map((k) => <Slider key={k} label={CONTROL_LABELS[k]} value={simulation.controls[k]} onChange={(n) => setCtl(k, n)} />)}
          {(Object.keys(EXTRA) as (keyof typeof EXTRA)[]).map((k) => <Slider key={k} label={EXTRA[k]} value={simulation.controls[k]} onChange={(n) => setCtl(k, n)} />)}
        </aside>
        <section className="space-y-4">
          {simulation.decisionPoints.map((dp) => {
            const branches = normalizeBranches(dp.branches);
            return (
              <div key={dp.id} className="panel">
                <div className="panel-header">
                  <div><span className="data mr-3 text-muted-foreground">{dp.year} · age {dp.age}</span><span className="font-serif text-lg">{dp.question}</span></div>
                  <span className="chip border-mock/40 bg-mock-soft text-mock">Prototype</span>
                </div>
                <div className="grid gap-px bg-border" style={{ gridTemplateColumns: branches.map((b) => `${Math.max(b.probability, 0.08)}fr`).join(" ") }}>
                  {branches.map((b) => (
                    <button key={b.id} onClick={() => choose(dp.id, b.id)} className={cn("bg-card p-3 text-left transition-colors hover:bg-accent", b.chosen && "bg-sim-soft")}>
                      <div className="data text-2xl">{Math.round(b.probability * 100)}%</div>
                      <div className="text-sm font-medium">{b.label}</div>
                      <div className="text-[11px] text-muted-foreground">{b.chosen ? "◆ Selected path" : b.rationale}</div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </section>
      </div>
    </>
  );
}
