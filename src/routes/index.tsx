import { createFileRoute, Link } from "@tanstack/react-router";
import { Plus, ArrowRight } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { MockBanner, PageHeader, Stat } from "@/components/lifespan/primitives";
import { STAGE_LABELS, WORKFLOW_STAGES } from "@/types/lifespan";
import { CLASS_LABELS } from "@/lib/defaults";
import { runAudits } from "@/features/audit/rules";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/")({
  head: pageHead("Dashboard", "Overview of LifeSpan episodes, facts, sources, assumptions and audit warnings."),
  component: Dashboard,
});

function Dashboard() {
  const { db, setActiveId } = useLifespan();
  const unresolved = db.facts.filter((f) => f.factType === "ASSUMPTION" && f.status !== "verified").length;
  const warnings = db.episodes.flatMap((e) => runAudits(db, e.id)).filter((a) => a.outcome !== "PASS").length;
  return (
    <>
      <PageHeader
        eyebrow="Workstation"
        title="Dashboard"
        description="Every life here separates facts, assumptions, simulation and story."
        actions={<Link to="/episodes/new" className="btn-primary px-4 py-2"><Plus className="h-4 w-4" /> Create New Life</Link>}
      />
      <MockBanner>The demo episode and all its numbers are prototype data — not research.</MockBanner>
      <div className="mb-8 grid grid-cols-5 gap-3">
        <Stat label="Episodes" value={db.episodes.length} />
        <Stat label="Facts" value={db.facts.length} hint={`${db.facts.filter((f) => f.factType === "FACT").length} typed FACT`} />
        <Stat label="Sources" value={db.sources.length} />
        <Stat label="Unresolved assumptions" value={unresolved} tone={unresolved ? "warn" : undefined} />
        <Stat label="Audit issues" value={warnings} tone={warnings ? "fail" : undefined} />
      </div>
      <div className="grid grid-cols-3 gap-6">
        <section className="col-span-2">
          <h2 className="mb-3 text-xl">Active episodes</h2>
          <div className="grid gap-3">
            {db.episodes.map((e) => {
              const pct = Math.round(((WORKFLOW_STAGES.indexOf(e.stage) + 1) / WORKFLOW_STAGES.length) * 100);
              return (
                <Link key={e.id} to="/dna" onClick={() => setActiveId(e.id)} className="panel group block p-4 transition-colors hover:border-foreground/30">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="font-serif text-lg leading-snug">{e.title}</div>
                      <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-muted-foreground">
                        <span>{e.character.country}</span>
                        <span className="data">b. {e.character.birthYear}</span>
                        <span>{CLASS_LABELS[e.character.startingClass]}</span>
                        <span>Modified {new Date(e.updatedAt).toLocaleDateString()}</span>
                      </div>
                    </div>
                    {e.isMock && <span className="chip border-mock/40 bg-mock-soft text-mock">Mock</span>}
                  </div>
                  <div className="mt-4 flex items-center gap-3">
                    <div className="h-1.5 flex-1 rounded-full bg-border"><div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} /></div>
                    <span className="data text-xs">{pct}%</span>
                    <span className="text-xs text-muted-foreground">{STAGE_LABELS[e.stage]}</span>
                    <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground" />
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
        <section>
          <h2 className="mb-3 text-xl">Recent activity</h2>
          <ol className="panel divide-y divide-border">
            {db.activity.slice(0, 10).map((a) => (
              <li key={a.id} className="flex gap-3 px-4 py-2.5">
                <span className="eyebrow w-20 shrink-0 pt-0.5">{a.kind}</span>
                <div className="min-w-0">
                  <div className="text-sm">{a.text}</div>
                  <div className="data text-[11px] text-muted-foreground">{new Date(a.at).toLocaleString()}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </>
  );
}
