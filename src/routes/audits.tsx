import { createFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, OutcomeChip, PageHeader, Stat } from "@/components/lifespan/primitives";
import { runAudits } from "@/features/audit/rules";
import type { AuditCategory } from "@/types/lifespan";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/audits")({
  head: pageHead("Audit Center", "Fact, timeline, economic, geographic, historical, story, assumption and bias audits."),
  component: Audits,
});

const CATS: AuditCategory[] = ["Fact", "Timeline", "Economic", "Geographic", "Historical", "Story", "Assumption", "Bias"];

function Audits() {
  const { db, active } = useLifespan();
  const results = useMemo(() => (active ? runAudits(db, active.id) : []), [db, active]);
  if (!active) return <EmptyEpisode />;
  const c = (o: string) => results.filter((r) => r.outcome === o).length;
  return (
    <>
      <PageHeader eyebrow="Pipeline · 9" title="Audit Center" description="Rules re-run live against current data. Items marked 'manual' await the Audit Worker." />
      <div className="mb-6 grid grid-cols-4 gap-3">
        <Stat label="Checks" value={results.length} />
        <Stat label="Pass" value={c("PASS")} />
        <Stat label="Warning" value={c("WARNING")} tone="warn" />
        <Stat label="Fail" value={c("FAIL")} tone="fail" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        {CATS.map((cat) => (
          <section key={cat} className="panel">
            <div className="panel-header"><h3 className="text-base">{cat} Audit</h3></div>
            <ul className="divide-y divide-border">
              {results.filter((r) => r.category === cat).map((r) => (
                <li key={r.id} className="flex gap-3 px-4 py-3">
                  <OutcomeChip o={r.outcome} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium">{r.title}</div>
                    <div className="text-xs text-muted-foreground">{r.explanation}</div>
                    {r.refs.length > 0 && <div className="data mt-1 text-[11px] text-foreground/70">refs: {r.refs.join(", ")}</div>}
                  </div>
                  <span className="eyebrow">{r.automated ? "rule" : "manual"}</span>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
