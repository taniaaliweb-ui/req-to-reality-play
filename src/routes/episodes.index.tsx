import { createFileRoute, Link } from "@tanstack/react-router";
import { Plus, Trash2 } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { PageHeader } from "@/components/lifespan/primitives";
import { STAGE_LABELS, WORKFLOW_STAGES, type WorkflowStage } from "@/types/lifespan";
import { CLASS_LABELS } from "@/lib/defaults";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/episodes/")({
  head: pageHead("Episodes", "All simulated lives in this LifeSpan workspace."),
  component: Episodes,
});

function Episodes() {
  const { db, mutate, activeId, setActiveId } = useLifespan();
  const setStage = (id: string, stage: WorkflowStage) =>
    mutate((d) => ({ ...d, episodes: d.episodes.map((e) => (e.id === id ? { ...e, stage, updatedAt: new Date().toISOString() } : e)) }), { kind: "episode", text: `Stage set to ${STAGE_LABELS[stage]}` });
  const remove = (id: string) => {
    if (!confirm("Delete this episode and all its records?")) return;
    mutate((d) => ({
      ...d,
      episodes: d.episodes.filter((e) => e.id !== id),
      facts: d.facts.filter((x) => x.episodeId !== id),
      timeline: d.timeline.filter((x) => x.episodeId !== id),
      tasks: d.tasks.filter((x) => x.episodeId !== id),
      economics: d.economics.filter((x) => x.episodeId !== id),
      chapters: d.chapters.filter((x) => x.episodeId !== id),
      simulations: d.simulations.filter((x) => x.episodeId !== id),
    }));
  };
  return (
    <>
      <PageHeader eyebrow="Library" title="Episodes" actions={<Link to="/episodes/new" className="btn-primary"><Plus className="h-4 w-4" /> New episode</Link>} />
      <div className="panel overflow-hidden">
        <table className="tbl">
          <thead><tr><th>Title</th><th>Country</th><th>Born</th><th>Class</th><th>Stage</th><th>Modified</th><th /></tr></thead>
          <tbody>
            {db.episodes.map((e) => (
              <tr key={e.id}>
                <td>
                  <Link to="/dna" onClick={() => setActiveId(e.id)} className="font-medium hover:text-primary">{e.title}</Link>
                  {e.isMock && <span className="chip ml-2 border-mock/40 bg-mock-soft text-mock">Mock</span>}
                  {e.id === activeId && <span className="chip ml-2 border-primary/30 text-primary">Active</span>}
                </td>
                <td>{e.character.country}</td>
                <td className="data">{e.character.birthYear}</td>
                <td>{CLASS_LABELS[e.character.startingClass]}</td>
                <td>
                  <select className="input py-0.5 text-xs" value={e.stage} onChange={(ev) => setStage(e.id, ev.target.value as WorkflowStage)}>
                    {WORKFLOW_STAGES.map((s) => <option key={s} value={s}>{STAGE_LABELS[s]}</option>)}
                  </select>
                </td>
                <td className="data text-xs text-muted-foreground">{new Date(e.updatedAt).toLocaleDateString()}</td>
                <td><button className="btn-ghost" onClick={() => remove(e.id)} aria-label="Delete"><Trash2 className="h-3.5 w-3.5" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
