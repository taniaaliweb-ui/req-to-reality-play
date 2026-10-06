"""LifeSpan Phase 6 simulation engine.

Pure, deterministic, seeded. Reads ONLY a frozen SimulationInput (built from a finalized dataset
snapshot + explicit assumptions + versioned provisional priors). Every state transition produces an
auditable SimulationEvent with its full probability trace. Outputs are always SIMULATED, never FACT.
"""
ENGINE_VERSION = "6.1.0"
