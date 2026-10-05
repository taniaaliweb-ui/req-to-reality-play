import type { CharacterTraits, SimulationControls } from "@/types/lifespan";

export const defaultTraits = (): CharacterTraits => ({
  ambition: 50,
  aptitude: 50,
  riskTolerance: 50,
  discipline: 50,
  socialSkills: 50,
  financialDiscipline: 50,
  resilience: 50,
  familyAttachment: 60,
  migrationWillingness: 40,
});

export const defaultControls = (): SimulationControls => ({
  realism: 75,
  randomness: 35,
  adversity: 50,
  upwardMobility: 50,
  downwardRisk: 40,
});

export const TRAIT_LABELS: Record<keyof CharacterTraits, string> = {
  ambition: "Ambition",
  aptitude: "Intelligence / aptitude",
  riskTolerance: "Risk tolerance",
  discipline: "Discipline",
  socialSkills: "Social skills",
  financialDiscipline: "Financial discipline",
  resilience: "Resilience",
  familyAttachment: "Family attachment",
  migrationWillingness: "Migration willingness",
};

export const CONTROL_LABELS: Record<keyof SimulationControls, string> = {
  realism: "Realism",
  randomness: "Randomness",
  adversity: "Adversity",
  upwardMobility: "Upward mobility potential",
  downwardRisk: "Downward mobility risk",
};

export const level = (n: number) => (n >= 67 ? "High" : n >= 34 ? "Medium" : "Low");

export const CLASS_LABELS = {
  poverty: "Poverty",
  working: "Working class",
  "lower-middle": "Lower-middle",
  middle: "Middle",
  "upper-middle": "Upper-middle",
  wealthy: "Wealthy",
} as const;
