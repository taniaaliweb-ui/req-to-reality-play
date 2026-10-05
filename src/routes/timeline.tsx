import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Lock, Unlock, Plus, Trash2, RefreshCw, X } from "lucide-react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { ConfidenceChip, EmptyEpisode, Field, MockBanner, PageHeader, SimChip } from "@/components/lifespan/primitives";
import type { Emotion, Level, LifeEventCategory, TimelineEvent } from "@/types/lifespan";
import { newId } from "@/services/lifespanApi";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/timeline")({
  head: pageHead("Life Timeline", "Chronological record of the simulated life with sources, confidence and simulation reasons."),
  component: Timeline,
});

export const CATEGORIES: LifeEventCategory[] = ["Career", "Relationships", "Finance", "Migration", "Health", "External", "Education", "Family", "Positive outlier", "Negative outlier"];
const EMOTIONS: Emotion[] = ["joy", "grief", "loneliness", "anxiety", "pride", "regret", "family responsibility", "migration isolation", "relationship stress", "financial pressure", "loss of status", "accomplishment"];

function Timeline() {
  const { active, mutate } = useLifespan();
  const { timeline } = useActiveRecords();
  const [edit, setEdit] = useState<TimelineEvent | null>(null);
  const [notice, setNotice] = useState("");
  if (!active) return <EmptyEpisode />;
  const born = active.character.birthYear;

  const upd = (id: string, p: Partial<TimelineEvent>) => mutate((d) => ({ ...d, timeline: d.timeline.map((e) => (e.id === id ? { ...e, ...p, updatedAt: new Date().toISOString() } : e)) }));
  const insert = () => {
    const last = timeline[timeline.length - 1];
    const year = (last?.year ?? born) + 1;
    setEdit({ id: "", createdAt: "", updatedAt: "", episodeId: active.id, year, age: year - born, location: last?.location ?? "", category: "Career", title: "", description: "", financialEffect: "", emotions: [], confidence: "low", factIds: [], simulationReason: "Manually inserted", locked: false });
  };
  const save = () => {
    if (!edit) return;
    const now = new Date().toISOString();
    const rec = { ...edit, age: edit.year - born, updatedAt: now };
    mutate((d) => edit.id ? { ...d, timeline: d.timeline.map((e) => (e.id === edit.id ? rec : e)) } : { ...d, timeline: [...d.timeline, { ...rec, id: newId("E"), createdAt: now }] }, { kind: "timeline", text: `Timeline event ${edit.id ? "edited" : "inserted"}: ${edit.title}` });
    setEdit(null);
  };
  const regenerate = () => {
    const unlocked = timeline.filter((e) => !e.locked).length;
    setNotice(`Regeneration requires the Simulation Engine (not implemented). ${unlocked} unlocked event(s) would be eligible; ${timeline.length - unlocked} locked event(s) would be preserved. Nothing was changed.`);
  };

  return (
    <>
      <PageHeader eyebrow="Pipeline · 6" title="Life Timeline" description={`${timeline.length} events · ${timeline.filter((e) => e.locked).length} locked`} actions={<><button className="btn" onClick={regenerate}><RefreshCw className="h-4 w-4" /> Regenerate unlocked</button><button className="btn-primary" onClick={insert}><Plus className="h-4 w-4" /> Insert event</button></>} />
      {active.isMock && <MockBanner>Events are a hand-authored prototype life, not engine output. Emotions are narrative interpretation, not measurements.</MockBanner>}
      {notice && <div className="mb-4 flex items-start gap-2 rounded-sm border border-warn/50 bg-assumption-soft px-3 py-2 text-xs"><span className="flex-1">{notice}</span><button onClick={() => setNotice("")}><X className="h-3.5 w-3.5" /></button></div>}
      <div className="grid grid-cols-[1fr_auto] gap-6">
        <ol className="relative ml-24 border-l border-foreground/20">
          {timeline.map((e) => (
            <li key={e.id} className="relative mb-3 pl-6">
              <div className="absolute -left-24 top-2 w-20 text-right">
                <div className="data text-lg leading-none">{e.year}</div>
                <div className="data text-[11px] text-muted-foreground">age {e.age}</div>
              </div>
              <span className={cn("absolute -left-[5px] top-3 h-2.5 w-2.5 rounded-full border-2 border-background", e.category === "External" ? "bg-fact" : e.category.includes("outlier") ? "bg-fail" : e.locked ? "bg-foreground" : "bg-primary")} />
              <div className={cn("panel p-3 transition-colors hover:border-foreground/30", edit?.id === e.id && "border-primary")}>
                <div className="flex items-start justify-between gap-3">
                  <button className="text-left" onClick={() => setEdit(e)}>
                    <div className="eyebrow">{e.category} · {e.location}</div>
                    <div className="font-serif text-lg leading-tight">{e.title}</div>
                  </button>
                  <div className="flex shrink-0 items-center gap-1">
                    <ConfidenceChip c={e.confidence} />
                    <button className="btn-ghost" title={e.locked ? "Unlock" : "Lock"} onClick={() => upd(e.id, { locked: !e.locked })}>{e.locked ? <Lock className="h-3.5 w-3.5 text-foreground" /> : <Unlock className="h-3.5 w-3.5" />}</button>
                    <button className="btn-ghost" disabled={e.locked} title={e.locked ? "Locked" : "Delete"} onClick={() => mutate((d) => ({ ...d, timeline: d.timeline.filter((x) => x.id !== e.id) }))}><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
                {e.description && <p className="mt-1 text-sm text-foreground/80">{e.description}</p>}
                <div className="mt-2 grid grid-cols-3 gap-3 text-xs">
                  <div><span className="text-muted-foreground">Financial: </span><span className="data">{e.financialEffect}</span></div>
                  <div><span className="text-muted-foreground">Emotional: </span><span className="italic">{e.emotions.join(", ") || "—"}</span></div>
                  <div><span className="text-muted-foreground">Facts: </span><span className="data">{e.factIds.join(", ") || "none"}</span></div>
                </div>
                <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground"><SimChip /> {e.simulationReason}</div>
              </div>
            </li>
          ))}
        </ol>
        {edit && (
          <aside className="panel sticky top-28 h-fit w-80 p-4">
            <div className="mb-3 flex items-center justify-between"><div className="eyebrow">{edit.id || "New event"}{edit.locked && " · locked"}</div><button className="btn-ghost" onClick={() => setEdit(null)}><X className="h-3.5 w-3.5" /></button></div>
            <fieldset disabled={edit.locked} className="space-y-3 disabled:opacity-60">
              <Field label="Title"><input className="input" value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Year"><input type="number" className="input data" value={edit.year} onChange={(e) => setEdit({ ...edit, year: Number(e.target.value) })} /></Field>
                <Field label="Category"><select className="input" value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value as LifeEventCategory })}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
              </div>
              <Field label="Location"><input className="input" value={edit.location} onChange={(e) => setEdit({ ...edit, location: e.target.value })} /></Field>
              <Field label="Description"><textarea rows={3} className="input" value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} /></Field>
              <Field label="Financial effect"><input className="input" value={edit.financialEffect} onChange={(e) => setEdit({ ...edit, financialEffect: e.target.value })} /></Field>
              <Field label="Emotional effect (narrative)">
                <div className="flex flex-wrap gap-1">{EMOTIONS.map((em) => <button type="button" key={em} onClick={() => setEdit({ ...edit, emotions: edit.emotions.includes(em) ? edit.emotions.filter((x) => x !== em) : [...edit.emotions, em] })} className={cn("rounded-sm border px-1.5 py-0.5 text-[11px]", edit.emotions.includes(em) ? "border-primary bg-accent text-primary" : "border-border text-muted-foreground")}>{em}</button>)}</div>
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Confidence"><select className="input" value={edit.confidence} onChange={(e) => setEdit({ ...edit, confidence: e.target.value as Level })}>{["high", "medium", "low"].map((c) => <option key={c}>{c}</option>)}</select></Field>
                <Field label="Fact refs"><input className="input data" value={edit.factIds.join(",")} onChange={(e) => setEdit({ ...edit, factIds: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></Field>
              </div>
              <Field label="Simulation reason"><input className="input" value={edit.simulationReason} onChange={(e) => setEdit({ ...edit, simulationReason: e.target.value })} /></Field>
              <button type="button" className="btn-primary w-full justify-center" onClick={save}>Save event</button>
            </fieldset>
          </aside>
        )}
      </div>
    </>
  );
}
