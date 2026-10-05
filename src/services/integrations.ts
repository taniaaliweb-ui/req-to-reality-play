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
  const prov = (id: string, name: string, fallback: string): Integration => {
    const p = providers?.find((x) => x.id === id);
    if (!online) return { name, status: "disabled", label: "Needs backend", description: fallback };
    if (!p) return { name, status: "checking", label: "Checking…", description: fallback };
    if (p.status === "import") return { name, status: "local", label: "Manual import", description: `${p.detail} · ${p.storedObservations} values stored` };
    return {
      name, status: p.status === "available" ? "online" : p.status === "disabled" ? "disabled" : "offline",
      label: p.status === "available" ? "Available" : p.status === "disabled" ? "Disabled" : p.status === "offline" ? "Offline" : "Error",
      description: `${p.dataset} · ${p.storedObservations} values stored${p.detail ? ` · ${p.detail}` : ""}`,
    };
  };
  engines.push(
    prov("ilostat", "ILOSTAT Provider", "Official ILO SDMX web service (free, no key)."),
    prov("uae-fcsc", "UAE Official Statistics", "FCSC .Stat — structured file import."),
    prov("india-mospi", "India MoSPI", "PLFS tables — structured CSV import."),
    { name: "Labor Evidence Engine", status: online ? "online" : mode === "local" ? "disabled" : "offline", label: online ? "Online" : mode === "local" ? "Needs backend" : "Offline", description: "Deterministic evidence matching, baselines, gaps (no AI)." },
    { name: "Dataset Snapshot Engine", status: online ? "online" : mode === "local" ? "disabled" : "offline", label: online ? "Online" : mode === "local" ? "Needs backend" : "Offline", description: "Immutable, versioned, hash-verified evidence snapshots." },
  );
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
    { name: "Simulation Engine", status: "not-configured", label: "Not implemented", description: "Life-event simulation not implemented; branches are hand-entered demo values." },
  ];
};
