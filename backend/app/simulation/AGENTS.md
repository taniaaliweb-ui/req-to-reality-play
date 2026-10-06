## Simulation engine rules
- A simulation reads only a frozen `simulation_inputs` row (finalized snapshot + snapshot assumptions + locked events + prior registry version; DB trigger blocks updates) — same input + seed + engine version must reproduce the same life.
- Randomness is one stream per (seed, year, domain) (`simulation/random.py`) — reproducible after restarts and lets branches resume mid-life.
- Every default probability/parameter is a versioned row in `simulation_priors`; rules never hard-code new probabilities — priors stay visible, editable and auditable.
- Every stochastic transition stores a `simulation_events` row with base → modifiers → final → draw and its evidence/assumption/prior ids; missing critical dimensions BLOCK instead of being filled.
- Simulation money uses Decimal per-currency ledgers that must reconcile exactly (opening + income − expenses + gains + transfers = closing); balances convert only with FX evidence in the snapshot.
- Story, production and receipts are generated without AI from the canonical run, every claim typed by provenance — narrative stays grounded in run data.
- Mortality prefers UN WPP abridged life tables (`providers/un_wpp_lifetable.py`, metrics LT_QX/LT_MX) with formula MORT-LT-ANNUAL; broad measures are a flagged fallback and every hazard stores lineage — age-specific evidence must never be silently bypassed.
- Simulation rule code may contain no untagged numeric literals: parameters go to the prior registry (with classification/units/provenance in `priors.META`), structural constants carry `# rule:<ID>` registered in `simulation/model_registry.py`; `scan_constants()` is enforced by tests — no hidden model logic.
- Frozen inputs that predate a registry key fall back to `priors.defaults()` (identical to the former inline values) — old inputs stay reproducible.
