import { CanonicalStory } from "@/components/lifespan/product";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, FactTypeChip, Field, PageHeader, StoryChip } from "@/components/lifespan/primitives";
import type { StoryChapter } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/story")({
  head: pageHead("Story Workspace", "Chapter editor built on the simulated timeline, with facts and assumptions visible."),
  component: Story,
});

const ENG = [["openQuestion", "Open question"], ["tension", "Tension"], ["decision", "Decision"], ["payoff", "Payoff"], ["transition", "Transition"]] as const;

function Story() {
  const { active, mutate } = useLifespan();
  const { chapters, timeline, facts } = useActiveRecords();
  const [sel, setSel] = useState(0);
  const [msg, setMsg] = useState("");
  if (!active) return <EmptyEpisode />;
  const ch = chapters[sel];
  const upd = (p: Partial<StoryChapter>) => ch && mutate((d) => ({ ...d, chapters: d.chapters.map((c) => (c.id === ch.id ? { ...c, ...p, updatedAt: new Date().toISOString() } : c)) }));
  const evs = ch ? timeline.filter((e) => ch.timelineEventIds.includes(e.id)) : [];
  const used = ch ? facts.filter((f) => ch.factIds.includes(f.id) || ch.assumptionIds.includes(f.id)) : [];

  return (
    <>
      <PageHeader eyebrow="Pipeline · 8" title="Story Workspace" description="Narrative is interpretation. It must stay traceable to timeline events and facts." actions={<button className="btn" onClick={() => setMsg("No Story Worker configured. LifeSpan will not generate placeholder prose and present it as AI output.")}><Sparkles className="h-4 w-4" /> Draft with AI</button>} />
      {msg && <div className="mb-4 rounded-sm border border-warn/50 bg-assumption-soft px-3 py-2 text-xs">{msg}</div>}
      <CanonicalStory eid={active.id} />
      <h2 className="mb-2 text-sm font-medium text-muted-foreground">Manual chapters (editable, legacy)</h2>
      <div className="grid grid-cols-[220px_1fr_300px] gap-5">
        <nav className="panel h-fit py-1">
          {chapters.map((c, i) => (
            <button key={c.id} onClick={() => setSel(i)} className={cn("flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent", i === sel && "bg-accent text-primary")}>
              <span className="data w-5 text-xs text-muted-foreground">{c.number}</span>
              <span className="flex-1 truncate">{c.title}</span>
              {c.text && <span className="h-1.5 w-1.5 rounded-full bg-pass" />}
            </button>
          ))}
        </nav>
        {ch ? (
          <>
            <article className="panel p-6">
              <div className="mb-2 flex items-center gap-2"><StoryChip /><span className="eyebrow">Chapter {ch.number}</span></div>
              <input className="mb-4 w-full bg-transparent font-serif text-3xl outline-none" value={ch.title} onChange={(e) => upd({ title: e.target.value })} />
              <textarea className="min-h-[420px] w-full resize-y bg-transparent font-serif text-[17px] leading-relaxed outline-none placeholder:text-muted-foreground" placeholder="Write this chapter from the referenced events and facts…" value={ch.text} onChange={(e) => upd({ text: e.target.value })} />
              <div className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4">
                <Field label="Emotional arc (interpretation)"><input className="input" value={ch.emotionalArc} onChange={(e) => upd({ emotionalArc: e.target.value })} /></Field>
                <Field label="Unresolved issues"><input className="input" value={ch.unresolved} onChange={(e) => upd({ unresolved: e.target.value })} /></Field>
              </div>
            </article>
            <aside className="space-y-4">
              <div className="panel p-3">
                <div className="eyebrow mb-2">Timeline references</div>
                {evs.length ? evs.map((e) => <div key={e.id} className="border-b border-dashed border-border py-1.5 text-xs last:border-0"><span className="data mr-2 text-muted-foreground">{e.year}</span>{e.title}</div>) : <div className="text-xs text-muted-foreground">None linked.</div>}
              </div>
              <div className="panel p-3">
                <div className="eyebrow mb-2">Facts & assumptions used</div>
                {used.length ? used.map((f) => <div key={f.id} className="flex items-start gap-2 py-1 text-xs"><FactTypeChip t={f.factType} /><span>{f.metric}</span></div>) : <div className="text-xs text-muted-foreground">None.</div>}
              </div>
              <div className="panel p-3">
                <div className="eyebrow mb-1">Engagement</div>
                <p className="mb-2 text-[11px] text-muted-foreground">Hooks only where the underlying life supports them. No artificial cliffhangers.</p>
                <div className="space-y-2">
                  {ENG.map(([k, l]) => <Field key={k} label={l}><input className="input text-xs" value={ch.engagement[k]} onChange={(e) => upd({ engagement: { ...ch.engagement, [k]: e.target.value } })} /></Field>)}
                </div>
              </div>
            </aside>
          </>
        ) : <div className="panel col-span-2 p-8 text-muted-foreground">No chapters.</div>}
      </div>
    </>
  );
}
