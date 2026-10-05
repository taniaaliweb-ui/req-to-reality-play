// Phase 6 dashboard panel for the active episode (backend mode).
import { Link } from "@tanstack/react-router";
import { useLifespan } from "@/hooks/useLifespan";
import { Stat } from "@/components/lifespan/primitives";
import { money, useBackend } from "@/components/lifespan/sim";
import { lifespanApi } from "@/services/lifespanApi";

const STEPS = [["Character DNA", "/dna"], ["Evidence", "/life-evidence"], ["Assumptions", "/life-evidence"], ["Dataset Snapshot", "/snapshots"], ["Simulation", "/simulation"],
  ["Explore Outcomes", "/simulation"], ["Canonical Life", "/simulation"], ["Audit", "/audits"], ["Story", "/story"], ["Production", "/production"], ["Life Receipt", "/receipt"]] as const;

export function EpisodeDashboard() {
  const { activeId, active } = useLifespan();
  const { data: d } = useBackend(() => lifespanApi.sim.dashboard(activeId), [activeId]);
  if (lifespanApi.mode !== "backend" || !active) return null;
  return (
    <section className="mb-8">
      <h2 className="mb-3 text-xl">{active.title}</h2>
      <div className="mb-3 flex flex-wrap gap-1 text-xs">{STEPS.map(([l, to], i) => <Link key={l} to={to} className="chip hover:bg-accent">{i + 1} {l}</Link>)}</div>
      {d && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Evidence snapshot" value={d.snapshot?.label ?? "none finalized"} />
          <Stat label="Simulation runs" value={d.simulationRuns.total} hint={`${d.simulationRuns.batch} in outcome batches · ${d.simulationRuns.branches} branches`} />
          <Stat label="Canonical life" value={d.canonical ? `died at ${d.canonical.deathAge ?? "—"}` : "not chosen"} hint={d.canonical?.stale ? "older configuration" : d.canonical?.id} tone={d.canonical?.stale ? "warn" : undefined} />
          <Stat label="Economic outcome" value={d.economicOutcome ? money(d.economicOutcome.netWorthAtDeath) : "—"} hint={d.economicOutcome?.position ? `position ${d.economicOutcome.position} (simulated)` : "simulated estate"} />
          <Stat label="Audit" value={d.audit ? `${d.audit.errors} errors` : "—"} hint={d.audit ? `${d.audit.warnings} warnings` : undefined} tone={d.audit?.errors ? "fail" : undefined} />
          <Stat label="Story" value={d.story ? `${d.story.chapters} chapters` : "not built"} hint={d.story ? `${d.story.beats} beats` : undefined} />
          <Stat label="Production" value={d.production ? `${d.production.scenes} scenes` : "not built"} hint={d.production?.edited ? "script edited" : undefined} />
          <Stat label="Research gaps" value={d.researchGaps} tone={d.researchGaps ? "warn" : undefined} />
        </div>
      )}
    </section>
  );
}
