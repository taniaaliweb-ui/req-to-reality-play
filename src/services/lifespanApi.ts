// LifeSpan API abstraction. UI talks ONLY to this interface.
// Phase 1: LocalLifespanApi persists to browser localStorage.
// Phase 2: HttpLifespanApi will call the backend at settings.backendUrl (http://localhost:8000).
import type { LifespanDB } from "@/types/lifespan";
import { buildDemoDB } from "@/mock/demoEpisode";

export interface LifespanApi {
  readonly mode: "local-prototype" | "http";
  load(): Promise<LifespanDB>;
  save(db: LifespanDB): Promise<void>;
  reset(): Promise<LifespanDB>;
}

const KEY = "lifespan.db.v1";

export class LocalLifespanApi implements LifespanApi {
  readonly mode = "local-prototype" as const;

  async load(): Promise<LifespanDB> {
    if (typeof window === "undefined") return buildDemoDB();
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return buildDemoDB();
    try {
      const parsed = JSON.parse(raw) as LifespanDB;
      return parsed.version === 1 ? parsed : buildDemoDB();
    } catch {
      return buildDemoDB();
    }
  }

  async save(db: LifespanDB): Promise<void> {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(KEY, JSON.stringify(db));
  }

  async reset(): Promise<LifespanDB> {
    const db = buildDemoDB();
    await this.save(db);
    return db;
  }
}

/** Placeholder for the future FastAPI/backend client. Not wired in Phase 1. */
export class HttpLifespanApi implements LifespanApi {
  readonly mode = "http" as const;
  constructor(private baseUrl: string) {}
  async load(): Promise<LifespanDB> {
    throw new Error(`Backend not implemented (would GET ${this.baseUrl}/db)`);
  }
  async save(): Promise<void> {
    throw new Error("Backend not implemented");
  }
  async reset(): Promise<LifespanDB> {
    throw new Error("Backend not implemented");
  }
}

export const lifespanApi: LifespanApi = new LocalLifespanApi();

export const newId = (prefix: string) =>
  `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
