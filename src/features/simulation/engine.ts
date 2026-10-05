// Simulation engine boundary. Phase 1 contains only pure helpers.
// The real engine (deterministic, seeded, data-driven) will live in the Python backend.
import type { SimulationBranch, SimulationRun } from "@/types/lifespan";

export const normalizeBranches = (b: SimulationBranch[]): SimulationBranch[] => {
  const total = b.reduce((a, x) => a + x.probability, 0) || 1;
  return b.map((x) => ({ ...x, probability: x.probability / total }));
};

export interface SimulationEngine {
  run(run: SimulationRun): Promise<never>;
}

export const simulationEngine: SimulationEngine = {
  async run() {
    throw new Error("Simulation engine not implemented (Phase 2+).");
  },
};
