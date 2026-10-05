import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { CharacterForm, DnaSummary } from "@/components/lifespan/CharacterForm";
import { PageHeader } from "@/components/lifespan/primitives";
import { defaultControls, defaultTraits } from "@/lib/defaults";
import { newId } from "@/services/lifespanApi";
import { scaffoldEpisode } from "@/features/episodes/scaffold";
import type { Character } from "@/types/lifespan";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/episodes/new")({
  head: pageHeadNew(),
  component: NewEpisode,
});

function pageHeadNew() {
  return () => ({
    meta: [
      { title: "Create New Life — LifeSpan" },
      { name: "description", content: "Configure the Character DNA for a new simulated life." },
      { property: "og:title", content: "Create New Life — LifeSpan" },
      { property: "og:description", content: "Configure the Character DNA for a new simulated life." },
    ],
  });
}

const STEPS = ["identity", "family", "traits", "controls", "review"] as const;
const STEP_LABEL = { identity: "Identity & class", family: "Family", traits: "Attributes", controls: "Simulation", review: "DNA summary" };

function NewEpisode() {
  const { mutate, setActiveId } = useLifespan();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [title, setTitle] = useState("");
  const [c, setC] = useState<Character>(() => ({
    id: "ch-new", createdAt: "", updatedAt: "", name: "Unnamed character", country: "", region: "", birthYear: 1980, gender: "unspecified", settlement: "urban", startingClass: "middle",
    family: { guardians: 2, siblings: 1, parentalIncomeClass: "middle", parentalEducation: "", housing: "" },
    traits: defaultTraits(), controls: defaultControls(),
  }));
  const current = STEPS[step];

  const create = () => {
    const now = new Date().toISOString();
    const createdId = newId("ep");
    mutate((db) => scaffoldEpisode(db, title || `${c.country || "Unknown"}, ${c.birthYear}`, { ...c, id: `ch-${createdId}`, createdAt: now, updatedAt: now }, createdId).db, { kind: "episode", text: `Episode created: ${title || c.country}` });
    setTimeout(() => {
      setActiveId(createdId);
      navigate({ to: "/research" });
    }, 0);
  };

  return (
    <>
      <PageHeader eyebrow="Step 1–2 of the pipeline" title="Create New Life" description="Define the Character DNA. No facts are generated — research tasks are scaffolded for you to fill." />
      <div className="mb-6 flex gap-1">
        {STEPS.map((s, i) => (
          <button key={s} onClick={() => setStep(i)} className={cn("flex-1 border-b-2 pb-2 text-left text-xs", i === step ? "border-primary text-foreground" : i < step ? "border-foreground/40 text-muted-foreground" : "border-border text-muted-foreground")}>
            <span className="data mr-1">{i + 1}</span> {STEP_LABEL[s]}
          </button>
        ))}
      </div>
      <div className="panel p-6">
        {current === "identity" && (
          <div className="mb-6">
            <label className="field-label">Episode title</label>
            <input className="input font-serif text-lg" placeholder="e.g. A Life in Lagos, 1985" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
        )}
        {current !== "review" ? (
          <CharacterForm value={c} onChange={setC} section={current} />
        ) : (
          <div className="grid grid-cols-2 gap-8">
            <div>
              <div className="eyebrow mb-2">Character DNA summary</div>
              <div className="font-serif text-xl mb-3">{title || "Untitled episode"}</div>
              <DnaSummary c={c} />
            </div>
            <div className="text-sm text-muted-foreground">
              <p className="mb-2">On creation, LifeSpan will:</p>
              <ul className="list-disc space-y-1 pl-5">
                <li>Create the episode at stage “Research Plan”.</li>
                <li>Scaffold research tasks across 8 categories (no values filled).</li>
                <li>Lock a single Birth event on the timeline.</li>
                <li>Create 12 empty story chapters.</li>
              </ul>
            </div>
          </div>
        )}
      </div>
      <div className="mt-4 flex justify-between">
        <button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</button>
        {step < STEPS.length - 1 ? (
          <button className="btn-primary" onClick={() => setStep(step + 1)}>Continue</button>
        ) : (
          <button className="btn-primary" disabled={!c.country} onClick={create}>{c.country ? "Create episode" : "Country required"}</button>
        )}
      </div>
    </>
  );
}
