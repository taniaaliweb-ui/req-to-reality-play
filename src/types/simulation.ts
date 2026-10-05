// Phase 6 simulation types (backend-only records). Every simulated value is SIMULATED, never FACT.
export type ProbClass = "EMPIRICAL" | "DERIVED_FROM_EMPIRICAL" | "ASSUMPTION_BASED" | "PROVISIONAL_SYSTEM_PRIOR" | "DETERMINISTIC";
export type Money = Record<string, string>;

export interface SimPrior {
  id: string; key: string; version: number; domain: string; name: string; description: string;
  parameter: Record<string, unknown>; enabled: boolean; active: boolean; notes: string; label: string; updatedAt: string;
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
  importance: number; explanation: string; scenarioOverride: boolean; ruleId: string;
}
export interface SimState {
  year: number; age: number; country: string; employment: string; currency: string; income: string; netWorth: string;
  economics: { totalIncome: string; totalExpenses: string; netWorth: Money; reconciliation: Record<string, { difference: string }>; householdSize: number; shortfall: string[];
    wageProvenance: { class: string; method: string; anchorId: string } | null; income: Record<string, string>; expenses: Record<string, string>; dependent?: boolean };
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
export interface Candidate { id: string; claim: string; value: string; unit: string; source: string; status: string; submittedBy: string; createdAt: string }
