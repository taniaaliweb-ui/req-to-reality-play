// Core LifeSpan domain types. All UI and services depend on these, never on providers.

export interface BaseRecord {
  id: string;
  createdAt: string;
  updatedAt: string;
}

export const WORKFLOW_STAGES = [
  "idea",
  "dna",
  "research",
  "sources",
  "facts",
  "timeline",
  "simulation",
  "story",
  "audit",
  "production",
  "receipt",
] as const;
export type WorkflowStage = (typeof WORKFLOW_STAGES)[number];

export const STAGE_LABELS: Record<WorkflowStage, string> = {
  idea: "Episode Idea",
  dna: "Character DNA",
  research: "Research Plan",
  sources: "Sources",
  facts: "Fact Ledger",
  timeline: "Life Timeline",
  simulation: "Simulation",
  story: "Story",
  audit: "Audit",
  production: "Production",
  receipt: "Life Receipt",
};

export type SocioClass =
  | "poverty"
  | "working"
  | "lower-middle"
  | "middle"
  | "upper-middle"
  | "wealthy";
export type Settlement = "urban" | "suburban" | "rural";
export type Gender = "male" | "female" | "non-binary" | "unspecified";
export type Level = "low" | "medium" | "high";

export interface CharacterTraits {
  ambition: number; // 0-100 simulation variable, not a measurement
  aptitude: number;
  riskTolerance: number;
  discipline: number;
  socialSkills: number;
  financialDiscipline: number;
  resilience: number;
  familyAttachment: number;
  migrationWillingness: number;
}

export interface SimulationControls {
  realism: number;
  randomness: number;
  adversity: number;
  upwardMobility: number;
  downwardRisk: number;
}

export interface Character extends BaseRecord {
  name: string;
  country: string;
  region: string;
  birthYear: number;
  gender: Gender;
  settlement: Settlement;
  startingClass: SocioClass;
  family: {
    guardians: number;
    siblings: number;
    parentalIncomeClass: SocioClass;
    parentalEducation: string;
    housing: string;
  };
  traits: CharacterTraits;
  controls: SimulationControls;
}

export interface Episode extends BaseRecord {
  title: string;
  stage: WorkflowStage;
  character: Character;
  isMock: boolean;
}

export type ResearchCategory =
  | "Demographics"
  | "Economy"
  | "Employment"
  | "Housing"
  | "Education"
  | "Migration"
  | "Social environment"
  | "Historical context";

export type TaskStatus = "pending" | "in-progress" | "complete" | "blocked";

export interface ResearchTask extends BaseRecord {
  episodeId: string;
  category: ResearchCategory;
  question: string;
  period: string;
  status: TaskStatus;
  assignedTo: string; // future agent name
  factIds: string[];
}

export type SourceType =
  | "government"
  | "World Bank"
  | "UN"
  | "OECD"
  | "academic"
  | "statistical agency"
  | "newspaper"
  | "historical archive"
  | "industry"
  | "other";
export type Reliability = "Primary" | "Strong" | "Moderate" | "Weak";

export interface Source extends BaseRecord {
  title: string;
  organization: string;
  url: string;
  publicationDate: string;
  accessedDate: string;
  geoCoverage: string;
  timeCoverage: string;
  type: SourceType;
  reliability: Reliability;
  notes: string;
}

export type FactType = "FACT" | "ESTIMATE" | "ASSUMPTION" | "DERIVED";
export type FactStatus = "verified" | "unverified" | "unresolved" | "disputed";

export interface Fact extends BaseRecord {
  episodeId: string;
  category: ResearchCategory;
  metric: string;
  value: string;
  unit: string;
  country: string;
  region: string;
  yearStart: number;
  yearEnd: number;
  sourceId: string | null;
  confidence: Level;
  factType: FactType;
  derivedFrom?: string;
  notes: string;
  status: FactStatus;
}

export type LifeEventCategory =
  | "Career"
  | "Relationships"
  | "Finance"
  | "Migration"
  | "Health"
  | "External"
  | "Education"
  | "Family"
  | "Positive outlier"
  | "Negative outlier";

export type Emotion =
  | "joy"
  | "grief"
  | "loneliness"
  | "anxiety"
  | "pride"
  | "regret"
  | "family responsibility"
  | "migration isolation"
  | "relationship stress"
  | "financial pressure"
  | "loss of status"
  | "accomplishment";

export interface TimelineEvent extends BaseRecord {
  episodeId: string;
  year: number;
  age: number;
  location: string;
  category: LifeEventCategory;
  title: string;
  description: string;
  financialEffect: string;
  emotions: Emotion[]; // narrative interpretation, NOT measured
  confidence: Level;
  factIds: string[];
  simulationReason: string;
  locked: boolean;
}

export type LifeEvent = TimelineEvent;

export interface EconomicYear {
  id: string;
  episodeId: string;
  year: number;
  age: number;
  income: number;
  spouseIncome: number;
  housing: number;
  food: number;
  education: number;
  healthcare: number;
  transport: number;
  familySupport: number;
  debt: number;
  savings: number;
  investments: number;
  assets: number;
  liabilities: number;
  currency: string;
  priceIndex: number; // mock index used for real-terms view (base year = 100)
}

export interface SimulationBranch {
  id: string;
  label: string;
  probability: number; // 0-1, PROTOTYPE values until engine exists
  rationale: string;
  chosen: boolean;
}

export interface SimulationRun extends BaseRecord {
  episodeId: string;
  seed: number;
  controls: SimulationControls & {
    careerVolatility: number;
    relationshipVolatility: number;
    healthIntensity: number;
  };
  decisionPoints: { id: string; age: number; year: number; question: string; branches: SimulationBranch[] }[];
  isPrototype: true;
}

export interface StoryChapter extends BaseRecord {
  episodeId: string;
  number: number;
  title: string;
  timelineEventIds: string[];
  factIds: string[];
  assumptionIds: string[];
  text: string;
  emotionalArc: string;
  unresolved: string;
  engagement: {
    openQuestion: string;
    tension: string;
    decision: string;
    payoff: string;
    transition: string;
  };
}

export type AuditCategory =
  | "Fact"
  | "Timeline"
  | "Economic"
  | "Geographic"
  | "Historical"
  | "Story"
  | "Assumption"
  | "Bias";
export type AuditOutcome = "PASS" | "WARNING" | "FAIL";

export interface AuditResult {
  id: string;
  category: AuditCategory;
  outcome: AuditOutcome;
  title: string;
  explanation: string;
  refs: string[];
  automated: boolean; // true = computed by deterministic rule in this build
}

export type AgentStatus = "not-configured" | "not-connected" | "disabled" | "local" | "connected";

export interface AgentRun extends BaseRecord {
  agent: string;
  task: string;
  status: "queued" | "running" | "done" | "failed";
}

export interface LifeReceipt {
  episodeId: string;
  born: number;
  died: number;
  age: number;
  countries: string[];
  education: string;
  career: string;
  lifetimeNominal: number;
  lifetimeReal: number;
  housingSpent: number;
  educationSpent: number;
  healthcareSpent: number;
  children: string;
  peakNetWorth: number;
  netWorthAtDeath: number;
  turningPoints: string[];
  losses: string[];
  achievements: string[];
  yearsWorking: number;
  yearsRetired: number;
  startingClass: SocioClass;
  endingClass: SocioClass;
  currency: string;
}

export interface ActivityItem {
  id: string;
  at: string;
  episodeId: string;
  kind: "research" | "fact" | "timeline" | "assumption" | "story" | "audit" | "episode";
  text: string;
}

export interface LifespanDB {
  version: number;
  episodes: Episode[];
  tasks: ResearchTask[];
  sources: Source[];
  facts: Fact[];
  timeline: TimelineEvent[];
  economics: EconomicYear[];
  simulations: SimulationRun[];
  chapters: StoryChapter[];
  activity: ActivityItem[];
  settings: AppSettings;
}

export interface AppSettings {
  backendUrl: string;
  hermesUrl: string;
  showMockBanners: boolean;
  defaultRealism: number;
  currencyDisplay: "local" | "USD";
}
