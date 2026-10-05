// Creates the empty scaffolding for a new episode. No facts are invented.
import type { Character, Episode, LifespanDB, ResearchCategory, ResearchTask, StoryChapter } from "@/types/lifespan";
import { newId } from "@/services/lifespanApi";

export const RESEARCH_TEMPLATE: Record<ResearchCategory, string[]> = {
  Demographics: ["Life expectancy by cohort", "Median age at first marriage", "Fertility rate"],
  Economy: ["Annual inflation (CPI)", "GDP per capita", "Exchange rates"],
  Employment: ["Wage levels by occupation", "Unemployment rate"],
  Housing: ["Rent levels", "Property prices"],
  Education: ["School enrolment & fees", "Higher education access"],
  Migration: ["Internal & international migration flows"],
  "Social environment": ["Family structure norms (sourced, avoid stereotypes)"],
  "Historical context": ["Major political/economic events in lifetime"],
};

export const CHAPTER_TITLES = ["Birth and Family", "Childhood", "Education", "Entering Adulthood", "Career", "Marriage and Family", "Crisis / Opportunity", "Migration", "Middle Age", "Later Life", "Death", "Life Receipt"];

export function scaffoldEpisode(db: LifespanDB, title: string, character: Character): { db: LifespanDB; id: string } {
  const now = new Date().toISOString();
  const id = newId("ep");
  const episode: Episode = { id, createdAt: now, updatedAt: now, title, stage: "research", character, isMock: false };
  const period = `${character.birthYear}–${character.birthYear + 80}`;
  const tasks: ResearchTask[] = Object.entries(RESEARCH_TEMPLATE).flatMap(([cat, qs]) =>
    qs.map((q) => ({ id: newId("RT"), createdAt: now, updatedAt: now, episodeId: id, category: cat as ResearchCategory, question: `${q} — ${character.country}`, period, status: "pending" as const, assignedTo: "Unassigned", factIds: [] })),
  );
  const chapters: StoryChapter[] = CHAPTER_TITLES.map((t, i) => ({
    id: newId("CH"), createdAt: now, updatedAt: now, episodeId: id, number: i + 1, title: t, timelineEventIds: [], factIds: [], assumptionIds: [], text: "", emotionalArc: "", unresolved: "",
    engagement: { openQuestion: "", tension: "", decision: "", payoff: "", transition: "" },
  }));
  return {
    id,
    db: {
      ...db,
      episodes: [episode, ...db.episodes],
      tasks: [...db.tasks, ...tasks],
      chapters: [...db.chapters, ...chapters],
      timeline: [
        ...db.timeline,
        { id: newId("E"), createdAt: now, updatedAt: now, episodeId: id, year: character.birthYear, age: 0, location: `${character.region}, ${character.country}`, category: "Family", title: "Birth", description: "Fixed by Character DNA.", financialEffect: "—", emotions: [], confidence: "high", factIds: [], simulationReason: "Character DNA", locked: true },
      ],
    },
  };
}
