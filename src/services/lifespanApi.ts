// LifeSpan API abstraction. UI talks ONLY to this module — pages never call fetch().
//
// Data mode (Vite env):
//   VITE_LIFESPAN_DATA_MODE=backend   -> HttpLifespanApi, canonical data in the local SQLite backend
//   VITE_LIFESPAN_DATA_MODE=local     -> LocalLifespanApi, browser storage (prototype/debug; default)
//   VITE_LIFESPAN_API_URL=http://127.0.0.1:8000
// In backend mode there is NO silent fallback to browser storage.
import type { AuditResult, BaselineInput, CandidateResult, DatasetSnapshot, EconomicBaseline, EconomicProfile, EconomicProfileInput, EngineResult, EvidenceGap, ExternalObservation, Household, ImportPreview, LifespanDB, LineageNode, ProviderInfo, Readiness, SnapshotDiff, SyncReport, VerifiedEconomics, WageDistribution, WageObservation } from "@/types/lifespan";
import { buildDemoDB } from "@/mock/demoEpisode";
import { diffWorkspace, type SyncOp } from "./sync";

export type DataMode = "local" | "backend";

export interface HealthStatus {
  online: boolean;
  database: "connected" | "unavailable" | "browser-storage";
  detail?: string;
}

export interface ImportReport {
  created: number;
  updated: number;
  skipped: number;
  conflicts: string[];
}

export interface LifespanApi {
  readonly mode: DataMode;
  load(): Promise<LifespanDB>;
  /** Persist the difference between two workspace states. */
  sync(prev: LifespanDB, next: LifespanDB): Promise<void>;
  reset(): Promise<LifespanDB>;
  health(): Promise<HealthStatus>;
  /** Canonical audits (backend). Local mode returns null → caller uses local rules. */
  getAudits(episodeId: string): Promise<AuditResult[] | null>;
  importWorkspace(db: LifespanDB, overwrite: boolean): Promise<ImportReport>;
  truth: TruthApi;
  labor: LaborApi;
}

export type ImportProvider = "manual" | "india-mospi" | "uae-fcsc";
/** Labour evidence, baselines and dataset snapshots (Phase 4). Backend only. */
export interface LaborApi {
  syncIlostat(req: { indicators: string[]; countries: string[]; yearStart: number; yearEnd: number }): Promise<SyncReport>;
  wageObservations(filter?: Record<string, string | number | undefined>): Promise<WageObservation[]>;
  distributions(country?: string): Promise<WageDistribution[]>;
  importPreview(provider: ImportProvider, csv: string): Promise<ImportPreview>;
  importCommit(provider: ImportProvider, csv: string): Promise<ImportPreview>;
  profiles(episodeId: string): Promise<EconomicProfile[]>;
  createProfile(episodeId: string, p: EconomicProfileInput): Promise<EconomicProfile>;
  updateProfile(id: string, p: EconomicProfileInput): Promise<EconomicProfile>;
  deleteProfile(id: string): Promise<void>;
  candidates(profileId: string, limit?: number): Promise<CandidateResult>;
  review(profileId: string, wageObservationId: string, decision: "rejected" | "flagged" | "clear", note?: string): Promise<unknown>;
  baselines(episodeId: string): Promise<EconomicBaseline[]>;
  createBaseline(episodeId: string, b: BaselineInput): Promise<EconomicBaseline>;
  approveBaseline(id: string, approved: boolean): Promise<EconomicBaseline>;
  deleteBaseline(id: string): Promise<void>;
  gaps(episodeId: string): Promise<EvidenceGap[]>;
  detectGaps(episodeId: string): Promise<EvidenceGap[]>;
  gapToTask(gapId: string): Promise<{ taskId: string; gap: EvidenceGap }>;
  readiness(episodeId: string): Promise<Readiness>;
  households(episodeId: string): Promise<Household[]>;
  createHousehold(episodeId: string, h: { label: string; yearStart: number; yearEnd: number; members: { role: string; name?: string; employmentKind?: string }[] }): Promise<Household>;
  addStream(householdId: string, s: Record<string, unknown>): Promise<Household>;
  deleteStream(id: string): Promise<void>;
  snapshots(episodeId: string): Promise<DatasetSnapshot[]>;
  createSnapshot(episodeId: string, name: string, notes?: string): Promise<DatasetSnapshot>;
  finalizeSnapshot(id: string): Promise<DatasetSnapshot>;
  refreshSnapshot(id: string): Promise<DatasetSnapshot>;
  newSnapshotVersion(id: string): Promise<DatasetSnapshot>;
  deleteSnapshot(id: string): Promise<void>;
  snapshotDetail(id: string): Promise<DatasetSnapshot & { facts: Record<string, unknown>[]; observations: Record<string, unknown>[]; baselines: EconomicBaseline[] }>;
  diffSnapshots(a: string, b: string): Promise<SnapshotDiff>;
}

export interface InflationRequest { episodeId?: string | undefined; country: string; amount: string; sourceYear: number; targetYear: number; currency?: string; save: boolean }
export interface FxRequest { episodeId?: string | undefined; amount: string; year: number; fromCountry: string; toCountry: string; save: boolean }

/** Truth + economic engine. All external data is fetched by the backend — never by the browser. */
export interface TruthApi {
  providers(check?: boolean): Promise<ProviderInfo[]>;
  syncWorldBank(req: { indicators: string[]; countries: string[]; yearStart: number; yearEnd: number }): Promise<SyncReport>;
  observations(filter?: { country?: string; indicator?: string }): Promise<ExternalObservation[]>;
  factsFromObservations(episodeId: string, observationIds: string[]): Promise<{ factIds: string[]; missingObservations: string[] }>;
  inflationAdjust(req: InflationRequest): Promise<EngineResult>;
  currencyConvert(req: FxRequest): Promise<EngineResult>;
  lineage(factId: string): Promise<LineageNode>;
  verifiedEconomics(episodeId: string, baseYear: number): Promise<VerifiedEconomics>;
  pinSnapshot(episodeId: string, label: string): Promise<{ id: string; items: unknown[] }>;
}

const backendOnly = () => Promise.reject(new ApiError(400, "Requires the LifeSpan backend (start it with ./scripts/start-local.sh)."));
const LOCAL_TRUTH: TruthApi = {
  providers: backendOnly, syncWorldBank: backendOnly, observations: backendOnly, factsFromObservations: backendOnly,
  inflationAdjust: backendOnly, currencyConvert: backendOnly, lineage: backendOnly, verifiedEconomics: backendOnly, pinSnapshot: backendOnly,
};
const LOCAL_LABOR = new Proxy({}, { get: () => backendOnly }) as LaborApi;

/** Thrown when the backend cannot be reached at all. */
export class BackendUnavailableError extends Error {
  constructor(public url: string) {
    super("LifeSpan backend unavailable");
  }
}

/** Thrown for HTTP errors. `message` is user-safe; `detail` is for the console. */
export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

export const LOCAL_STORAGE_KEY = "lifespan.db.v1";

export class LocalLifespanApi implements LifespanApi {
  readonly mode = "local" as const;
  readonly truth = LOCAL_TRUTH;
  readonly labor = LOCAL_LABOR;

  async load(): Promise<LifespanDB> {
    return readLocalWorkspace() ?? buildDemoDB();
  }
  async sync(_prev: LifespanDB, next: LifespanDB): Promise<void> {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(next));
  }
  async reset(): Promise<LifespanDB> {
    const db = buildDemoDB();
    await this.sync(db, db);
    return db;
  }
  async health(): Promise<HealthStatus> {
    return { online: false, database: "browser-storage", detail: "Local prototype mode — backend not used." };
  }
  async getAudits(): Promise<null> {
    return null;
  }
  async importWorkspace(): Promise<ImportReport> {
    throw new ApiError(400, "Import is only available in backend mode.");
  }
}

/** Reads Phase 1 browser data if present (used for import into the backend). */
export function readLocalWorkspace(): LifespanDB | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(LOCAL_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as LifespanDB;
    return parsed.version === 1 ? parsed : null;
  } catch {
    return null;
  }
}

export class HttpLifespanApi implements LifespanApi {
  readonly mode = "backend" as const;
  readonly truth: TruthApi;
  readonly labor: LaborApi;
  constructor(private baseUrl: string) {
    const enc = encodeURIComponent;
    const qs = (f: Record<string, string | number | undefined> = {}) => {
      const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString();
      return q ? `?${q}` : "";
    };
    this.labor = {
      syncIlostat: (req) => this.req("POST", "/data/ilostat/sync", req),
      wageObservations: (f) => this.req("GET", `/labor/wage-observations${qs(f)}`),
      distributions: (country) => this.req("GET", `/labor/distributions${qs({ country })}`),
      importPreview: (provider, csv) => this.req("POST", "/labor/import/preview", { provider, csv }),
      importCommit: (provider, csv) => this.req("POST", "/labor/import/commit", { provider, csv }),
      profiles: (eid) => this.req("GET", `/episodes/${enc(eid)}/economic-profiles`),
      createProfile: (eid, p) => this.req("POST", `/episodes/${enc(eid)}/economic-profiles`, p),
      updateProfile: (id, p) => this.req("PUT", `/economic-profiles/${enc(id)}`, p),
      deleteProfile: (id) => this.req("DELETE", `/economic-profiles/${enc(id)}`),
      candidates: (pid, limit = 25) => this.req("GET", `/economic-profiles/${enc(pid)}/candidates?limit=${limit}`),
      review: (pid, wageObservationId, decision, note = "") => this.req("POST", `/economic-profiles/${enc(pid)}/reviews`, { wageObservationId, decision, note }),
      baselines: (eid) => this.req("GET", `/episodes/${enc(eid)}/baselines`),
      createBaseline: (eid, b) => this.req("POST", `/episodes/${enc(eid)}/baselines`, b),
      approveBaseline: (id, approved) => this.req("POST", `/baselines/${enc(id)}/approve?approved=${approved}`),
      deleteBaseline: (id) => this.req("DELETE", `/baselines/${enc(id)}`),
      gaps: (eid) => this.req("GET", `/episodes/${enc(eid)}/evidence-gaps`),
      detectGaps: (eid) => this.req("POST", `/episodes/${enc(eid)}/evidence-gaps/detect`),
      gapToTask: (gid) => this.req("POST", `/evidence-gaps/${enc(gid)}/research-task`),
      readiness: (eid) => this.req("GET", `/episodes/${enc(eid)}/readiness`),
      households: (eid) => this.req("GET", `/episodes/${enc(eid)}/households`),
      createHousehold: (eid, h) => this.req("POST", `/episodes/${enc(eid)}/households`, h),
      addStream: (hid, st) => this.req("POST", `/households/${enc(hid)}/streams`, st),
      deleteStream: (id) => this.req("DELETE", `/income-streams/${enc(id)}`),
      snapshots: (eid) => this.req("GET", `/episodes/${enc(eid)}/snapshots`),
      createSnapshot: (eid, name, notes = "") => this.req("POST", `/episodes/${enc(eid)}/snapshots`, { name, notes }),
      finalizeSnapshot: (id) => this.req("POST", `/snapshots/${enc(id)}/finalize`),
      refreshSnapshot: (id) => this.req("POST", `/snapshots/${enc(id)}/refresh`),
      newSnapshotVersion: (id) => this.req("POST", `/snapshots/${enc(id)}/new-version`),
      deleteSnapshot: (id) => this.req("DELETE", `/snapshots/${enc(id)}`),
      snapshotDetail: (id) => this.req("GET", `/snapshots/${enc(id)}`),
      diffSnapshots: (a, b) => this.req("GET", `/snapshots/diff${qs({ a, b })}`),
    };
    this.truth = {
      providers: (check = false) => this.req("GET", `/data/providers${check ? "?check=true" : ""}`),
      syncWorldBank: (req) => this.req("POST", "/data/world-bank/sync", req),
      observations: (f = {}) => {
        const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as [string, string][]).toString();
        return this.req("GET", `/data/observations${q ? `?${q}` : ""}`);
      },
      factsFromObservations: (eid, ids) => this.req("POST", `/episodes/${enc(eid)}/facts/from-observations`, { observationIds: ids }),
      inflationAdjust: (req) => this.req("POST", "/economics/inflation-adjust", req),
      currencyConvert: (req) => this.req("POST", "/economics/currency-convert", req),
      lineage: (fid) => this.req("GET", `/facts/${enc(fid)}/lineage`),
      verifiedEconomics: (eid, baseYear) => this.req("GET", `/episodes/${enc(eid)}/economics/verified?baseYear=${baseYear}`),
      pinSnapshot: (eid, label) => this.req("POST", `/episodes/${enc(eid)}/dataset-snapshots`, { label }),
    };
  }

  private async req<T>(method: string, path: string, body?: unknown): Promise<T> {
    let res: Response;
    try {
      const init: RequestInit = { method };
      if (body !== undefined) {
        init.headers = { "Content-Type": "application/json" };
        init.body = JSON.stringify(body);
      }
      res = await fetch(`${this.baseUrl}/api/v1${path}`, init);
    } catch (e) {
      console.error("[lifespanApi] network error", method, path, e);
      throw new BackendUnavailableError(this.baseUrl);
    }
    if (!res.ok) {
      let detail: unknown = undefined;
      try {
        detail = await res.json();
      } catch {
        /* non-JSON error */
      }
      console.error("[lifespanApi] HTTP", res.status, method, path, detail);
      const msg =
        typeof (detail as { detail?: unknown })?.detail === "string" && res.status !== 500
          ? String((detail as { detail: string }).detail)
          : res.status === 404 ? "Record not found." : res.status === 422 ? "The backend rejected invalid data." : res.status === 409 ? "That record already exists." : "The backend could not complete the request.";
      throw new ApiError(res.status, msg, detail);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  load() {
    return this.req<LifespanDB>("GET", "/snapshot");
  }

  async sync(prev: LifespanDB, next: LifespanDB) {
    for (const op of diffWorkspace(prev, next)) {
      try {
        await this.apply(op);
      } catch (e) {
        if (op.kind === "delete" && e instanceof ApiError && e.status === 404) continue; // already gone
        throw e;
      }
    }
  }

  private apply(op: SyncOp) {
    return op.kind === "put" ? this.req("PUT", op.path, op.body) : op.kind === "post" ? this.req("POST", op.path, op.body) : this.req("DELETE", op.path);
  }

  async reset(): Promise<LifespanDB> {
    throw new ApiError(400, "Reset is disabled in backend mode to protect the database.");
  }

  async health(): Promise<HealthStatus> {
    try {
      const h = await this.req<{ status: string; database: string }>("GET", "/health");
      return { online: h.status === "ok", database: h.database === "connected" ? "connected" : "unavailable" };
    } catch {
      return { online: false, database: "unavailable", detail: `No response from ${this.baseUrl}` };
    }
  }

  getAudits(episodeId: string) {
    return this.req<AuditResult[]>("GET", `/episodes/${encodeURIComponent(episodeId)}/audits`);
  }

  importWorkspace(db: LifespanDB, overwrite: boolean) {
    return this.req<ImportReport>("POST", "/import", { data: db, overwrite });
  }
}

const env = import.meta.env as Record<string, string | undefined>;
export const DATA_MODE: DataMode = env["VITE_LIFESPAN_DATA_MODE"] === "backend" ? "backend" : "local";
export const API_URL = (env["VITE_LIFESPAN_API_URL"] ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export const lifespanApi: LifespanApi = DATA_MODE === "backend" ? new HttpLifespanApi(API_URL) : new LocalLifespanApi();

export const newId = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
