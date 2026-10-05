import { createFileRoute } from "@tanstack/react-router";
import { useLifespan } from "@/hooks/useLifespan";
import { CharacterForm, DnaSummary } from "@/components/lifespan/CharacterForm";
import { EmptyEpisode, PageHeader } from "@/components/lifespan/primitives";
import { pageHead } from "@/lib/seo";
import type { Character } from "@/types/lifespan";

export const Route = createFileRoute("/dna")({
  head: pageHead("Character DNA", "Identity, family, traits and simulation controls for the active life."),
  component: Dna,
});

function Dna() {
  const { active, mutate } = useLifespan();
  if (!active) return <EmptyEpisode />;
  const update = (c: Character) =>
    mutate((db) => ({ ...db, episodes: db.episodes.map((e) => (e.id === active.id ? { ...e, character: { ...c, updatedAt: new Date().toISOString() }, updatedAt: new Date().toISOString() } : e)) }));
  return (
    <>
      <PageHeader eyebrow="Pipeline · 2" title="Character DNA" description={active.title} />
      <div className="grid grid-cols-[1fr_340px] gap-6">
        <div className="panel p-6"><CharacterForm value={active.character} onChange={update} /></div>
        <aside className="panel sticky top-28 h-fit p-5">
          <div className="eyebrow mb-3">Summary</div>
          <DnaSummary c={active.character} />
        </aside>
      </div>
    </>
  );
}
