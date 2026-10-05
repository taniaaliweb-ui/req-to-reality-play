import type { AgentStatus } from "@/types/lifespan";

export interface Integration {
  name: string;
  status: AgentStatus;
  endpoint?: string;
  description: string;
}

// Honest status: nothing external is connected in Phase 1.
export const getIntegrations = (backendUrl: string, hermesUrl: string): Integration[] => [
  { name: "LifeSpan Backend", status: "not-connected", endpoint: backendUrl, description: "Episode DB, Fact Ledger, deterministic Python calculations." },
  { name: "Supervisor AI", status: "not-configured", description: "Plans research and orchestrates workers." },
  { name: "Hermes", status: "not-connected", endpoint: hermesUrl, description: "Agent runtime." },
  { name: "Research Worker", status: "not-configured", description: "Finds sources and proposes facts." },
  { name: "Story Worker", status: "not-configured", description: "Drafts chapters from timeline + facts." },
  { name: "Audit Worker", status: "not-configured", description: "Semantic audits beyond local rules." },
  { name: "MCP Server", status: "disabled", description: "Tool access for datasets & calculators." },
  { name: "Database", status: "local", description: "Browser localStorage prototype store." },
];
