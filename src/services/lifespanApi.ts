// LifeSpan API abstraction. UI talks ONLY to this module — pages never call fetch().
//
// Data mode (Vite env):
//   VITE_LIFESPAN_DATA_MODE=backend   -> HttpLifespanApi, canonical data in the local SQLite backend
//   VITE_LIFESPAN_DATA_MODE=local     -> LocalLifespanApi, browser storage (prototype/debug; default)
//   VITE_LIFESPAN_API_URL=http://127.0.0.1:8000
// In backend mode there is NO silent fallback to browser storage.
import type { AuditResult, LifespanDB } from "@/types/lifespan";
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
}

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
  constructor(private baseUrl: string) {}

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
        res.status === 404 ? "Record not found." : res.status === 422 ? "The backend rejected invalid data." : res.status === 409 ? "That record already exists." : "The backend could not complete the request.";
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
