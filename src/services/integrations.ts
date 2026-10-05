import type { AgentStatus, ProviderInfo } from "@/types/lifespan";
import type { DataMode, HealthStatus } from "./lifespanApi";

export interface Integration {
  name: string;
  status: AgentStatus | "online" | "offline" | "checking";
  label: string;
  endpoint?: string;
  description: string;
}

// Honest status: only the backend and database are real. Future systems are never shown online.
export const getIntegrations = (mode: DataMode, apiUrl: string, hermesUrl: string, health: HealthStatus | null, providers: ProviderInfo[] | null = null): Integration[] => {
  const backend: Integration =
    mode === "local"
      ? { name: "LifeSpan Backend", status: "disabled", label: "Not used (local mode)", endpoint: apiUrl, description: "Set VITE_LIFESPAN_DATA_MODE=backend to use it." }
      : !health
        ? { name: "LifeSpan Backend", status: "checking", label: "Checking…", endpoint: apiUrl, description: "FastAPI REST API, validation, audits." }
        : { name: "LifeSpan Backend", status: health.online ? "online" : "offline", label: health.online ? "Online" : "Offline", endpoint: apiUrl, description: health.online ? "FastAPI REST API, validation, audits." : (health.detail ?? "Unreachable.") };
  const database: Integration =
    mode === "local"
      ? { name: "Database", status: "local", label: "Browser storage", description: "Phase 1 prototype store in this browser only." }
      : { name: "Database", status: health?.database === "connected" ? "online" : "offline", label: health?.database === "connected" ? "Local SQLite" : "Unavailable", description: "backend/data/lifespan.db" };
  const online = mode === "backend" && !!health?.online;
  const wb = providers?.find((p) => p.id === "world-bank");
  const engines: Integration[] = [
    { name: "Truth Engine", status: online ? "online" : mode === "local" ? "disabled" : "offline", label: online ? "Online" : mode === "local" ? "Needs backend" : "Offline", description: "Observations → sourced facts → lineage." },
    { name: "Economic Engine", status: online ? "online" : mode === "local" ? "disabled" : "offline", label: online ? "Online" : mode === "local" ? "Needs backend" : "Offline", description: "Deterministic inflation + annual-average FX (engine 1.0)." },
    {
      name: "World Bank Provider",
      status: !online ? "disabled" : !wb ? "checking" : wb.status === "available" ? "online" : wb.status === "disabled" ? "disabled" : "offline",
      label: !online ? "Needs backend" : !wb ? "Checking…" : wb.status === "available" ? "Available" : wb.status === "disabled" ? "Disabled" : wb.status === "offline" ? "Offline" : "Error",
      description: wb ? `World Development Indicators · ${wb.storedObservations} values stored locally` : "World Development Indicators (no API key).",
    },
  ];
  return [
    backend,
    database,
    ...engines,
    { name: "Supervisor AI", status: "not-configured", label: "Not configured", description: "Plans research and orchestrates workers." },
    { name: "Hermes", status: "not-connected", label: "Not connected", endpoint: hermesUrl, description: "Agent runtime." },
    { name: "Research Worker", status: "not-configured", label: "Not configured", description: "Finds sources and proposes facts." },
    { name: "Story Worker", status: "not-configured", label: "Not configured", description: "Drafts chapters from timeline + facts." },
    { name: "Audit Worker", status: "not-configured", label: "Not configured", description: "Semantic audits beyond deterministic rules." },
    { name: "MCP Server", status: "disabled", label: "Disabled", description: "Tool access for datasets & calculators." },
    { name: "Simulation Engine", status: "not-configured", label: "Prototype only", description: "Life-event simulation not implemented; branches are hand-entered demo values." },
  ];
};
