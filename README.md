# LifeSpan — Phase 1 (application foundation)

Research workstation for historically grounded life simulations. Phase 1 is a local-first prototype: UI, workflow, typed data model, and clean integration seams. **No AI, backend, Hermes, or MCP is connected.**

## Prerequisites
- macOS (Apple Silicon M1+ supported), Node 20+ (or Bun). No Docker. No cloud account.

## Install & run
```bash
npm install
npm run dev        # dev server (port set by the Vite config; override with --port 3000)
```
Data persists in browser `localStorage` (`lifespan.db.v1`). Reset via Settings → "Reset to demo data".

## Architecture
```text
src/
  types/lifespan.ts          Domain model (Episode, Character, Fact, Source, TimelineEvent, …)
  mock/demoEpisode.ts        ONE clearly-labelled mock episode (all numbers illustrative)
  services/
    lifespanApi.ts           Data API interface — LocalLifespanApi (now), HttpLifespanApi (stub)
    aiProvider.ts            Provider-agnostic AI interface — NotConfiguredProvider
    integrations.ts          Honest integration status (System Status page)
  features/
    audit/rules.ts           Deterministic audit rules (run live)
    economics/calc.ts        Deterministic money math (nominal/real)
    receipt/derive.ts        Life Receipt derivation
    simulation/engine.ts     Engine boundary (not implemented)
    episodes/scaffold.ts     New-episode scaffolding (no invented facts)
  hooks/useLifespan.tsx      App state, persistence via lifespanApi
  components/lifespan/       Shell, primitives, Character DNA form
  routes/                    One file per page (TanStack Router file routes)
```

## Environment variables (future)
```text
LIFESPAN_BACKEND_URL=http://localhost:8000
HERMES_URL=http://127.0.0.1:8642
OPENAI_API_KEY / ANTHROPIC_API_KEY   # backend only — never in the browser
```

## Future connections
- **Backend**: implement `HttpLifespanApi` against `http://localhost:8000` and swap the export in `lifespanApi.ts`. Simulation, inflation, currency and purchasing-power math run there in deterministic Python.
- **Hermes**: the backend talks to Hermes (`http://127.0.0.1:8642`); the UI only sees agent runs via the API.
- **MCP**: the backend exposes/consumes MCP tools (datasets, calculators). The UI never calls MCP directly.

## Epistemic rule
FACT · ESTIMATE · ASSUMPTION · DERIVED · SIMULATION · STORY are always visually distinct and never silently mixed.
