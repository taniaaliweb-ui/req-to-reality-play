import { createFileRoute } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, MockBanner, PageHeader } from "@/components/lifespan/primitives";
import { RESEARCH_TEMPLATE } from "@/features/episodes/scaffold";
import type { ResearchCategory, TaskStatus } from "@/types/lifespan";
import { newId } from "@/services/lifespanApi";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/research")({
  head: pageHead("Research Plan", "Research categories and tasks required to ground the active life."),
  component: Research,
});

const statusStyle: Record<TaskStatus, string> = {
  pending: "border-border text-muted-foreground",
  "in-progress": "border-warn/50 text-warn",
  complete: "border-pass/50 text-pass",
  blocked: "border-fail/50 text-fail",
};

function Research() {
  const { active, mutate } = useLifespan();
  const { tasks } = useActiveRecords();
  if (!active) return <EmptyEpisode />;
  const cats = Object.keys(RESEARCH_TEMPLATE) as ResearchCategory[];
  const done = tasks.filter((t) => t.status === "complete").length;
  const setStatus = (id: string, status: TaskStatus) =>
    mutate((d) => ({ ...d, tasks: d.tasks.map((t) => (t.id === id ? { ...t, status, updatedAt: new Date().toISOString() } : t)) }), status === "complete" ? { kind: "research", text: "Research task completed" } : undefined);
  const add = (category: ResearchCategory) => {
    const q = prompt(`New ${category} research question`);
    if (!q) return;
    const now = new Date().toISOString();
    mutate((d) => ({ ...d, tasks: [...d.tasks, { id: newId("RT"), createdAt: now, updatedAt: now, episodeId: active.id, category, question: q, period: "", status: "pending", assignedTo: "Unassigned", factIds: [] }] }));
  };
  return (
    <>
      <PageHeader eyebrow="Pipeline · 3" title="Research Plan" description={`${done} of ${tasks.length} tasks complete. Research is performed manually until the Research Worker is configured.`} />
      {active.isMock && <MockBanner>Task statuses are illustrative; no real research has been conducted.</MockBanner>}
      <div className="grid grid-cols-2 gap-4">
        {cats.map((cat) => {
          const list = tasks.filter((t) => t.category === cat);
          return (
            <section key={cat} className="panel">
              <div className="panel-header">
                <h3 className="text-base">{cat}</h3>
                <button className="btn-ghost" onClick={() => add(cat)}><Plus className="h-3 w-3" /> Task</button>
              </div>
              <ul className="divide-y divide-border">
                {list.length === 0 && <li className="px-4 py-3 text-xs text-muted-foreground">No tasks.</li>}
                {list.map((t) => (
                  <li key={t.id} className="flex items-start gap-3 px-4 py-2.5">
                    <div className="min-w-0 flex-1">
                      <div className="text-sm">{t.question}</div>
                      <div className="data mt-0.5 text-[11px] text-muted-foreground">{t.id} · {t.period || "—"} · {t.factIds.length} fact(s) · {t.assignedTo}</div>
                    </div>
                    <select value={t.status} onChange={(e) => setStatus(t.id, e.target.value as TaskStatus)} className={cn("chip cursor-pointer bg-card", statusStyle[t.status])}>
                      {(["pending", "in-progress", "complete", "blocked"] as const).map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </>
  );
}
