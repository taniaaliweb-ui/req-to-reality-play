// Phase 6 simulation types (backend-only records). Every simulated value is SIMULATED, never FACT.
export type ProbClass = "EMPIRICAL" | "DERIVED_FROM_EMPIRICAL" | "ASSUMPTION_BASED" | "PROVISIONAL_SYSTEM_PRIOR" | "DETERMINISTIC";
export type Money = Record<string, string>;

export interface SimPrior {
  id: string; key: string; version: number; domain: string; name: string; description: string;
  parameter: Record<string, unknown>; enabled: boolean; active: boolean; notes: string; label: string; updatedAt: string;
  classification?: PriorClassification; units?: Record<string, string>; provenance?: string;
}
export type PriorClassification = "EMPIRICAL" | "DERIVED" | "USER_ASSUMPTION" | "PROVISIONAL_MODEL_PRIOR" | "DETERMINISTIC_ACCOUNTING_RULE";
export interface WageStep { step: string; label: string; value?: string; factor?: string; currency?: string; coverage?: string; classification: string; componentClass?: string; sourceIds?: string[] }
export interface Lineage {
  method?: string; kind?: string; country?: string; year?: number; sourceYear?: number; sex?: string; age?: number; ageGroup?: string; ageGroupSpan?: number | null;
  sourceIndicator?: string; sourceValue?: string | null; observationIds?: string[]; formula?: string; formulaId?: string; formulaVersion?: string;
  annualProbability?: number; finalAnnualProbability?: number; projection?: boolean; ageSpecificAvailable?: boolean;
  chain?: WageStep[]; anchorCoverage?: string; referenceWage?: string; currency?: string; referenceClass?: string;
}
export interface ReviewDimension {
  key: string; label: string; critical: boolean; evidenceStatus: string; simulationStatus: string; evidenceCount: number;
  assumptionIds: string[]; unusableAssumptionIds: string[]; priorIds: string[]; resolution: string[]; reasons: string[]; needsAcknowledgement: boolean;
}
export interface InputReview {
  snapshot: { id: string; label: string; version: number; contentHash: string | null };
  config: Record<string, number>; locks: { id: string; year: number; title: string; kind: string | null }[];
  assumptions: { id: string; domain: string; claim: string; value?: string; unit?: string; parsed: { kind: string } }[];
  dimensions: ReviewDimension[]; blocked: string[]; canRun: boolean; needsAcknowledgement: string[]; priorLabel: string; note: string;
}
export interface SimInput { id: string; datasetSnapshotId: string; snapshotLabel: string; masterSeed: number; config: Record<string, number>; createdAt: string; contentHash: string; priorRegistryVersion: string; simulationEngineVersion: string }
export interface Outcome {
  deathYear: number | null; deathAge: number | null; lifetimeEarnings: Money; lifetimeSpending: Money; peakIncome: Money; peakNetWorth: Money; netWorthAtDeath: Money;
  finalCurrency: string; yearsEmployed: number; yearsUnemployed: number; yearsRetired: number; retirementAge: number | null; children: number; migrated: boolean;
  homeOwner: boolean; businessAttempt: boolean; businessSuccess: boolean; married: boolean; divorced: boolean; countries: string[]; education: string;
  economicPosition: string | null; fingerprint: string; outliers: { year: number; type: string; sign: string }[];
}
export interface AuditItem { ruleId: string; severity: "error" | "warning"; message: string; year?: number | null }
export interface SimRun {
  id: string; episodeId: string; inputId: string; seed: number; engineVersion: string; kind: string; status: string; batchId: string | null;
  parentRunId: string | null; branchYear: number | null; overrides: { type: string }[]; label: string; outcome: Outcome;
  qualityReport: Record<string, unknown>; audit: AuditItem[]; isCanonical: boolean; startedAt: string;
}
export interface SimEvent {
  id: string; seq: number; year: number; age: number; domain: string; eventType: string; probability: number | null; baseProbability: number | null;
  probabilityClass: ProbClass; evidenceIds: string[]; assumptionIds: string[]; priorIds: string[]; factIds: string[];
  modifiers: { label: string; kind: "add" | "mult"; value: number; source: string }[]; randomDraw: number | null; outcome: string; occurred: boolean;
  importance: number; explanation: string; scenarioOverride: boolean; ruleId: string; lineage?: Lineage | null;
}
export interface SimState {
  year: number; age: number; country: string; employment: string; currency: string; income: string; netWorth: string;
  economics: { totalIncome: string; totalExpenses: string; netWorth: Money; reconciliation: Record<string, { difference: string }>; householdSize: number; shortfall: string[];
    wageProvenance: { class: string; method: string; anchorId: string; anchorCoverage?: string; chain?: WageStep[] } | null; income: Record<string, string>; expenses: Record<string, string>; dependent?: boolean };
}
export interface Stat { n: number; min: number; p10: number; median: number; p90: number; max: number; mean: number }
export interface SimJob {
  id: string; status: string; total: number; done: number; progress: number; error: string | null;
  result: null | { runs: number; disclaimer: string; deathAge: Stat | null; yearsEmployed: Stat | null; yearsUnemployed: Stat | null; retirementAge: Stat | null; children: Stat | null;
    money: Record<string, Record<string, Stat | null>>; rates: Record<string, number>; outliers: Record<string, number>; memberRunIds: string[];
    representative?: { currency: string; median: string; strong: string; weak: string; unusual: string; note: string } };
}
export interface CanonicalStatus { canonical: SimRun | null; stale: boolean; reasons: string[]; message?: string }
export interface StoryClaim { id: string; text: string; type: string; refs: string[]; year: number | null }
export interface StoryResult {
  label: string; runId: string; chapters: { key: string; number: number; title: string; yearStart: number | null; yearEnd: number | null; draft: string; questions: string[]; claimIds: string[] }[];
  beats: { id: string; year: number; age: number; chapterTitle: string; setup: string | null; tension: string | null; decision: string | null; consequence: string; payoff: string | null; emotionalInterpretation: { labels: string[] } }[];
  claims: StoryClaim[]; audit: { ruleId: string; severity: string; message: string }[];
}
export interface ProductionResult {
  summary: string; outline: { number: number; title: string; years: (number | null)[]; questions: string[] }[];
  scenes: { sceneNumber: number; chapter: string; year: number | null; age: number | null; location: string; narration: string; visualConcept: string; estimatedDuration: number; sourceIds: string[]; labels: string[] }[];
  script: string; edited: boolean; visualNotes: string[]; narrationNotes: string[];
  check: { wordCount: number; estimatedRuntimeSeconds: number; warnings: { ruleId: string; message: string }[]; chapters: string[] };
}
export type Receipt2 = Record<string, unknown> & { provenance: Record<string, unknown>; label: string };
export interface Candidate {
  id: string; claim: string; value: string; unit: string; source: string; url?: string; location?: string; periodStart?: number | null; periodEnd?: number | null;
  status: string; submittedBy: string; createdAt: string; acceptedAs?: string | null; reviewedScope?: Record<string, unknown> | null; links?: Record<string, string>;
}
export interface ReviewForm {
  acceptAs: "FACT" | "ESTIMATE" | "CONTEXT" | "ASSUMPTION" | "REJECT"; country?: string; region?: string; yearStart?: number | undefined; yearEnd?: number | undefined; population?: string;
  value?: string | undefined; unit?: string | undefined; domain?: string; metric?: string; sex?: string; lifeStage?: string | undefined; sourceTitle?: string; sourceOrganization?: string;
  sourceType?: string; reliability?: string; url?: string; confidence?: string; note?: string;
}
export interface Replacement { id: string; episodeId: string; candidateId: string; targetKind: "ASSUMPTION" | "PRIOR"; targetId: string; message: string; status: string; newSnapshotId: string | null; newRunId: string | null; createdAt: string }
export interface McpTool { name: string; description: string; riskClass: "READ" | "SAFE_WRITE" | "CONSEQUENTIAL_WRITE" | "PROHIBITED"; group: string; enabled: boolean }
export interface McpPermissions { config: { profile: string; enabledGroups: string[]; consequential: "REQUIRE_APPROVAL" | "ALLOW" | "DENY" }; tools: McpTool[]; groups: string[]; riskClasses: string[]; profiles: Record<string, string[]> }
export interface McpApproval { id: string; tool: string; arguments: Record<string, unknown>; status: string; result: Record<string, unknown> | null; createdAt: string; decidedAt: string | null; riskClass: string }
export interface ModelValidation {
  simulationEngineVersion: string; economicEngineVersion: string; priorRegistryVersion: string; classifications: string[]; activePriors: SimPrior[];
  priorsByClassification: Record<string, string[]>; empiricalInputs: { input: string; usedBy: string; source: string; transformation: string }[];
  empiricalParameters: SimPrior[]; assumptionParameters: { id: string; domain: string; claim: string; value: string; unit: string; years: (number | null)[]; classification: string }[];
  deterministicRules: { id: string; description: string; parameter?: Record<string, unknown>; occurrences: { file: string; line: number; value: string }[] }[];
  methodology: Record<string, string[]>; knownLimitations: string[];
  constantScan: { status: "PASS" | "FAIL"; unregistered: { file: string; line: number; value: string; code: string }[]; taggedCount: number; filesScanned: string[] };
  episode: null | { id: string; canonical: null | { runId: string; mortalityMethodYears: Record<string, number> };
    snapshotInputs: null | { snapshot: { id: string; label: string; contentHash: string | null }; lifeTable: Record<string, { years: number; first: number; last: number }>; series: Record<string, Record<string, number>>; cpiCountries: string[]; fxCountries: string[]; wageAnchors: number } };
  note: string;
}
export interface DashboardData {
  snapshot: { id: string; label: string } | null;
  simulationRuns: { total: number; batch: number; branches: number };
  canonical: { id: string; deathAge: number | null; stale: boolean } | null;
  economicOutcome: { netWorthAtDeath: Money; position: string | null } | null;
  audit: { errors: number; warnings: number } | null;
  story: { chapters: number; beats: number } | null;
  production: { scenes: number; edited: boolean } | null;
  researchGaps: number;
}
