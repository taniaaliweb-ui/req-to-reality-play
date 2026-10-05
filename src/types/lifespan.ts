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
  // Phase 3 provenance (optional: Phase 1/2 records don't have them)
  currency?: string | null;
  externalObservationId?: string | null;
  provider?: string | null;
  dataset?: string | null;
  indicatorCode?: string | null;
  /** true = demo/mock value, never verified history */
  isPrototype?: boolean;
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
  externalDataEnabled?: boolean;
  worldBankEnabled?: boolean;
  ilostatEnabled?: boolean;
  uaeStatEnabled?: boolean;
  unWppEnabled?: boolean;
  simulationRequiredDomains?: string[];
}

// ---------- Phase 3: truth + economic engine (backend-only data) ----------
export interface ExternalObservation {
  id: string;
  provider: string;
  dataset: string;
  indicatorCode: string;
  indicatorName: string;
  countryCode: string;
  countryName: string;
  year: number;
  value: string; // decimal string, full provider precision
  unit: string;
  sourceOrganization: string;
  sourceNote: string;
  license: string;
  sourceUrl: string;
  providerLastUpdated: string;
  retrievedAt: string;
  rawMetadata: Record<string, unknown>;
  revisions: number;
}

export interface ProviderInfo {
  id: string;
  name: string;
  dataset: string;
  authentication: string;
  status: "available" | "offline" | "error" | "disabled" | "unknown" | "import";
  mode?: "LIVE_API" | "AVAILABLE_IMPORT" | "MANUAL";
  liveApi?: string | null;
  detail: string;
  enabled: boolean;
  storedObservations: number;
  indicators: { code: string; name: string; unit: string; kind: string; precisionNote: string; dims?: string[] }[];
  lastSync: { at: string; status: string; summary: Record<string, unknown> } | null;
}

export interface SyncReport {
  provider: string;
  status: "ok" | "partial" | "error";
  startedAt: string;
  finishedAt: string;
  retrieved: number;
  unavailable: number;
  error?: string;
  indicators: { indicator: string; retrieved: number; unavailable: number | null; created?: number; unchanged?: number; revised?: number; error?: string; unknownCountries?: string[]; missing?: { country: string; year: number; reason: string }[] }[];
}

export interface EngineResult {
  status: "OK" | "MISSING_DATA" | "INVALID_INPUT";
  calculationType: string;
  formula: string;
  formulaVersion: string;
  engineVersion: string;
  result: string | null;
  display: string | null;
  parameters: Record<string, unknown>;
  inputs: { role: string; value: string; year?: number }[];
  missing: string[];
  errors: string[];
  labels: string[];
  observations: ExternalObservation[];
  factId?: string;
  calculationId?: string;
}

export interface LineageNode {
  fact: { id: string; metric: string; value: string; unit: string; factType: FactType; status: FactStatus; year: number; country: string; isPrototype: boolean; provider: string | null; indicatorCode: string | null };
  source: { id: string; title: string; organization: string; url: string; reliability: Reliability } | null;
  observation: ExternalObservation | null;
  calculation: {
    id: string; type: string; formula: string; formulaVersion: string; engineVersion: string; parameters: Record<string, unknown>;
    labels: string[]; createdAt: string; storedResult: string | null; recomputedResult: string | null; reproducible: boolean;
    inputs: (LineageNode & { role: string })[];
  } | null;
}

export interface VerifiedEconomics {
  baseYear: number;
  engineVersion: string;
  formulas: string[];
  note: string;
  years: { year: number; currency: string; country: string | null; nominalHousehold: string; nominalIsPrototype: true; real: string | null; usd: string | null; missing: string[] }[];
}

// ---------- Phase 4: labour evidence (backend-only data) ----------
export type LifeStageKey = "birth-family" | "education" | "first-employment" | "migration-wage" | "housing" | "retirement";
export const LIFE_STAGES: { key: LifeStageKey; label: string }[] = [
  { key: "birth-family", label: "Birth / family economy" },
  { key: "education", label: "Education" },
  { key: "first-employment", label: "First employment" },
  { key: "migration-wage", label: "Migration wage" },
  { key: "housing", label: "Housing" },
  { key: "retirement", label: "Retirement" },
];

export interface WageObservation {
  id: string; externalObservationId: string; provider: string; country: string; region: string | null; year: number; period: string; frequency: string;
  statisticType: "MEAN" | "MEDIAN" | "DISTRIBUTION" | "OTHER"; payPeriod: string; value: string | null; currency: string | null; nominalOrReal: string;
  grossOrNet: "GROSS" | "NET" | "UNKNOWN"; employeeScope: string | null; occupationCode: string | null; occupationLabel: string | null;
  occupationClassification: string | null; industryCode: string | null; industryLabel: string | null; industryClassification: string | null;
  educationCode: string | null; educationLabel: string | null; educationClassification: string | null; sex: string | null; ageGroup: string | null;
  ruralUrban: string | null; citizenship: string | null; migrantStatus: string | null; formalInformal: string | null; employmentStatus: string | null;
  fullPartTime: string | null; sourcePopulation: string; surveyName: string | null; confidence: string; notes: string; retrievedAt?: string | null;
}

export interface WageDistribution {
  id: string; provider: string; dataset: string; country: string; year: number; metric: string; payPeriod: string; currency: string | null;
  dimensions: Record<string, string>; sourceOrganization: string; sourceUrl: string; yearDistance?: number;
  bins: { lowerBound: string | null; upperBound: string | null; openLower: boolean; openUpper: boolean; count: string | null; share: string | null; unit: string; currency: string | null }[];
}

export interface EconomicProfile {
  id: string; episodeId: string; lifeStage: LifeStageKey; lifeStageLabel: string; targetYear: number; yearStart: number; yearEnd: number;
  country: string; region: string; urbanRural: "" | "URBAN" | "RURAL"; educationLevel: "" | "LTB" | "BAS" | "INT" | "ADV"; occupation: string;
  occupationCode: string; occupationClassification: "ISCO-08" | "ISCO-88"; industry: string; industryCode: string;
  employmentStatus: "" | "EMPLOYEE" | "SELF_EMPLOYED" | "EMPLOYER" | "UNPAID" | "UNKNOWN"; formalInformal: "" | "FORMAL" | "INFORMAL";
  yearsExperience: number | null; age: number | null; sex: "" | "MALE" | "FEMALE"; citizenship: "" | "NATIONAL" | "NON_NATIONAL";
  migrantStatus: string; employmentSector: string; notes: string;
}
export type EconomicProfileInput = Omit<EconomicProfile, "id" | "episodeId" | "lifeStageLabel">;

export interface MatchCandidate {
  wage: WageObservation; score: number; breakdown: { dimension: string; points: number; max: number; note: string }[];
  yearDistance: number; sourceYear: number; targetYear: number; countryMatch: boolean; label: string;
  review: { decision: "rejected" | "flagged"; note: string } | null;
}
export interface CandidateResult { profile: EconomicProfile; candidates: MatchCandidate[]; totalConsidered: number; distributions: WageDistribution[]; note: string }

export interface EconomicBaseline {
  id: string; episodeId: string; profileId: string | null; lifeStage: LifeStageKey; lifeStageLabel: string; yearStart: number; yearEnd: number;
  employmentType: string; occupation: string; baselineType: "FACT_SUPPORTED" | "ASSUMPTION" | "DERIVED"; estimateKind: "POINT" | "RANGE" | "DISTRIBUTION";
  low: string | null; high: string | null; point: string | null; currency: string; payPeriod: string; grossOrNet: string;
  annualization: { method: string; assumptions: Record<string, unknown>; low: string | null; high: string | null; point: string | null } | null;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA"; confidenceReasons: string[]; reasoning: string;
  evidence: { wageObservationId: string; observationId: string; factId: string; score: number; yearDistance: number; sourceYear: number; value: string; population: string; derivedFactId?: string; derivedValue?: string }[];
  sourceFactIds: string[]; derivedCalculationIds: string[]; assumptionFactId: string | null; userApproved: boolean; approvedAt: string | null;
  createdAt: string; pinnedInSnapshot: string | null;
  temporalCoverage?: WageAnchorCoverage;
  prototypeIncome: { isPrototype: true; note: string; years: { year: number; income: number; spouseIncome: number; currency: string }[] };
}
export interface BaselineInput {
  profileId?: string | null; lifeStage: LifeStageKey; yearStart: number; yearEnd: number; baselineType: EconomicBaseline["baselineType"];
  wageObservationIds?: string[]; adjustToYear?: number | null; low?: string; high?: string; point?: string; currency?: string; payPeriod?: string;
  reasoning?: string; occupation?: string; annualization?: { assumptions: Record<string, string> } | null;
}

export interface EvidenceGap {
  id: string; episodeId: string; gapKey: string; title: string; reason: string; category: string; country: string; yearStart: number; yearEnd: number;
  priority: "HIGH" | "MEDIUM" | "LOW"; status: "open" | "resolved"; auto: boolean; researchTaskId: string | null; createdAt: string;
  domain?: string | null; lifeStage?: string | null; targetPopulation?: string | null;
}
export interface Readiness { stages: { stage: LifeStageKey; label: string; status: "READY" | "PARTIAL" | "MISSING"; reasons: string[] }[]; overall: number; note: string }

export interface ImportPreview {
  rowsDetected: number; valid: number; invalid: number; duplicates: number; changed: number; errors: string[]; template: string[]; imported?: number;
  rows: { line: number; status: "valid" | "invalid" | "duplicate" | "changed"; errors: string[]; data: Record<string, string> }[];
}

export interface Household {
  id: string; episodeId: string; label: string; yearStart: number; yearEnd: number;
  members: { id: string; role: string; name: string; employmentKind: string }[];
  streams: { id: string; memberId: string | null; kind: string; yearStart: number; yearEnd: number; low: string | null; high: string | null; currency: string | null; payPeriod: string | null; basis: string; baselineId: string | null; factId: string | null; notes: string }[];
}

export interface DatasetSnapshot {
  id: string; episodeId: string; name: string; status: "draft" | "final"; version: number; parentId: string | null; notes: string; createdAt: string;
  finalizedAt: string | null; contentHash: string | null; intact: boolean | null;
  counts: { facts: number; verifiedFacts: number; assumptions: number; derived: number; observations: number; observationsByProvider: Record<string, number>; baselines: number; approvedBaselines: number };
}
export interface SnapshotDiffItem { kind: "added" | "removed" | "changed" | "unchanged"; id: string; label: string; old?: string; new?: string }
export interface SnapshotDiff { from: DatasetSnapshot; to: DatasetSnapshot; observations: SnapshotDiffItem[]; facts: SnapshotDiffItem[]; baselines: SnapshotDiffItem[] }

// ---------- Phase 5: life-context evidence (backend-only data) ----------
export type Coverage = "DIRECT" | "NEARBY" | "DERIVED" | "ASSUMED" | "MISSING";
export type CellStatus = "READY" | "PARTIAL" | "MISSING" | "NOT_APPLICABLE";
export interface YearCoverage { year: number; coverage: Coverage; sourceYear: number | null; distance: number | null; note?: string; closestEvidenceYear?: number | null }
export interface WageAnchorCoverage {
  semantics: "WAGE_ANCHOR" | "ASSUMPTION" | "NONE"; anchors: { year: number; value: string; population: string; statisticType: string; observationId: string }[];
  directCoverage: number[]; stage: [number, number]; windowYears: number; years: YearCoverage[]; counts: Record<string, number>; unresolvedYears: number[]; note: string;
}
export interface MatchScore { score: number; breakdown: { dimension: string; points: number; max: number; note: string }[]; yearDistance: number; countryMatch: boolean; label: string }
export interface LifeObservation {
  id: string; externalObservationId: string | null; domain: string; metric: string; metricLabel: string; value: string; unit: string; country: string;
  region: string | null; geoLevel: "NATIONAL" | "REGION" | "CITY"; year: number; sex: string | null; ageGroup: string | null; educationLevel: string | null;
  urbanRural: string | null; incomeGroup: string | null; category: string | null; originCountry: string | null; destinationCountry: string | null;
  populationScope: string; observationType: string; provider: string; dataset: string; source: string; sourceOrganization: string; isPrototype: boolean;
  notes: string; statisticKind: "POPULATION_STATISTIC"; match?: MatchScore; outsideWindow?: boolean;
}
export interface MatrixCell {
  domain: string; label: string; critical: boolean; windowYears: number; windowReason: string; status: CellStatus; reasons: string[];
  coverage: YearCoverage[]; counts?: Record<Coverage, number>; supportingCount?: number; assumptionCount?: number; gapCount?: number;
  supporting?: (LifeObservation & Record<string, unknown>)[]; candidates?: LifeObservation[]; extra?: Record<string, unknown>[];
  assumptions?: AssumptionRecord[]; gaps?: EvidenceGap[]; researchTasks?: { id: string; question: string; status: string }[];
}
export interface MatrixStage { stage: string; label: string; yearStart: number; yearEnd: number; basis: string; applicable: boolean; countries: string[]; cities: string[]; status: CellStatus; cells: MatrixCell[] }
export interface LifeMatrix { plan: { origin: string; birthYear: number; moves: { year: number; country: string; city: string }[] }; stages: MatrixStage[]; domains: { key: string; label: string }[]; note: string }
export interface ReadinessV2 {
  overall: "READY" | "PARTIAL" | "NOT_READY"; required: string[]; blocking: string[]; note: string;
  groups: { key: string; label: string; status: "READY" | "PARTIAL" | "NOT_READY" | "NOT_APPLICABLE"; required: boolean; ready: number; partial: number; missing: number }[];
  stages: { stage: string; label: string; status: CellStatus }[];
}
export interface AssumptionRecord {
  id: string; episodeId: string; kind: "register" | "fact"; domain: string; lifeStage: string; claim: string; value: string; unit: string;
  yearStart: number | null; yearEnd: number | null; reason: string; createdBy: string; createdAt: string; confidence: string; status: string;
  includedInSnapshots: string[]; isPrototype?: boolean;
}
export interface AssumptionInput { domain: string; lifeStage: string; claim: string; value?: string; unit?: string; yearStart?: number; yearEnd?: number; reason: string; confidence?: "HIGH" | "MEDIUM" | "LOW" }
export interface HistoricalEventRec {
  id: string; name: string; category: string; geography: string[]; region: string | null; startDate: string; endDate: string | null; economicRelevance: string;
  description: string; sources: { organization: string; title: string; url: string }[]; verification: "verified" | "unverified";
  matches?: { stage: string; label: string; relevance: "RELEVANT" | "POSSIBLY_RELEVANT"; reason: string }[]; relevant?: boolean;
}
export interface PolicyRec {
  id: string; country: string; policyType: string; title: string; effectiveStart: string; effectiveEnd: string | null; description: string; source: string;
  sourceOrganization: string; sourceUrl: string; factType: string; confidence: string; verification: "verified" | "unverified"; notes: string;
}
export interface ContextRec {
  id: string; topic: string; country: string; region: string | null; yearStart: number; yearEnd: number; populationScope: string; claim: string; source: string;
  sourceUrl: string; evidenceType: string; confidence: string; dataKind: string;
}
export interface LifeObsSummary { domain: string; country: string; provider: string; count: number; yearMin: number; yearMax: number }
export interface MigrationPathEvidence {
  id: string; origin: string; destination: string; yearStart: number; yearEnd: number; notes: string; auto: boolean; observations: LifeObservation[];
  bilateralObservations: number; policies: PolicyRec[]; destinationWageYears: number[]; missing: string[]; note: string;
}
export interface LifeImportPreview { rows: { line: number; row: Record<string, string>; errors: string[] }[]; errors: string[]; valid: number; header: string[]; committed?: number }
export interface SnapshotManifest { title: string; status: string; contentHash: string | null; lines: { label: string; count: number }[]; readiness: { overall: string; groups: { label: string; status: string }[] } | null; phase5Contents: boolean }
