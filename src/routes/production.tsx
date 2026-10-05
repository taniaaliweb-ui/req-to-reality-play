import { ExportPanel, ProductionWorkspace } from "@/components/lifespan/product";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, PageHeader } from "@/components/lifespan/primitives";
import { runAudits } from "@/features/audit/rules";
import { pageHead } from "@/lib/seo";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/production")({
  head: pageHead("Production", "Readiness checklist for turning a simulated life into a documentary episode."),
  component: Production,
});

function Production() {
  const { db, active } = useLifespan();
  const { chapters, facts, tasks } = useActiveRecords();
  if (!active) return <EmptyEpisode />;
  const audits = runAudits(db, active.id);
  const checks = [
    { label: "All research tasks complete", ok: tasks.every((t) => t.status === "complete"), to: "/research" },
    { label: "No unsourced facts", ok: !facts.some((f) => (f.factType === "FACT" || f.factType === "ESTIMATE") && !f.sourceId), to: "/facts" },
    { label: "No unresolved assumptions", ok: !facts.some((f) => f.factType === "ASSUMPTION" && f.status !== "verified"), to: "/facts" },
    { label: "All chapters drafted", ok: chapters.every((c) => c.text.trim().length > 0), to: "/story" },
    { label: "No failing audits", ok: !audits.some((a) => a.outcome === "FAIL"), to: "/audits" },
    { label: "Human editorial sign-off", ok: false, to: "/production" },
  ] as const;
  return (
    <>
      <PageHeader eyebrow="Pipeline · 10" title="Production" description="Script export, narration, visuals and video assembly arrive in later phases. Production Workspace built from the canonical life: summary, outline, script editor, scenes, notes and exports." />
      <ProductionWorkspace eid={active.id} />
      <ExportPanel eid={active.id} />
      <div className="grid grid-cols-[1fr_1fr] gap-6">
        <div className="panel divide-y divide-border">
          {checks.map((c) => (
            <Link key={c.label} to={c.to} className="flex items-center gap-3 px-4 py-3 hover:bg-accent/40">
              <span className={cn("chip", c.ok ? "border-pass bg-pass text-primary-foreground" : "border-border text-muted-foreground")}>{c.ok ? "Ready" : "Open"}</span>
              <span className="text-sm">{c.label}</span>
            </Link>
          ))}
        </div>
        <div className="panel hatch-mock p-5 text-sm">
          <div className="eyebrow mb-2">Not yet implemented</div>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Script export (Markdown / Fountain)</li><li>Narration & voice</li><li>Archive visual sourcing</li><li>Data graphics generation</li><li>Edit decision list</li>
          </ul>
        </div>
      </div>
    </>
  );
}
