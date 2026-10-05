<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture rules
- UI reads/writes data only through `src/services/lifespanApi.ts`; pages never call fetch — one boundary shared by future agents/MCP.
- In backend mode the FastAPI+SQLite backend (`backend/`) is canonical; never fall back to browser storage silently — avoids two sources of truth.
- Frontend persists by diffing workspace states into REST upserts/deletes (`src/services/sync.ts`) — pages keep their mutate() model.
- Backend schema changes go through Alembic migrations in `backend/migrations/` — the user's local DB must upgrade in place.
- External statistics are fetched only by backend providers (`backend/app/providers/`) behind the DataProvider interface and stored raw in `external_observations` before becoming facts — keeps every number traceable and offline-capable.
- Economic math lives only in `backend/app/services/economic_engine.py` (pure, Decimal, versioned formulas); every saved result gets a `derived_calculations` row plus `calculation_inputs` — results must stay reproducible after formulas change.
- Labour statistics become `wage_observations` (NULL = dimension not published); character income exists only as an `economic_baselines` row (FACT_SUPPORTED / DERIVED / ASSUMPTION) — source statistic, assumption and simulated income must stay separate.
- Evidence matching (`backend/app/services/labor.py`) is deterministic and explainable, never AI — rankings must be reproducible.
- Finalized dataset snapshots are immutable (service check + SQLite triggers + content hash); changes create a new version — future simulations must run on pinned data. Batch-altering snapshot tables drops the triggers, so recreate them in that migration.
- Core features must use only free official sources or local code; paid or AI services may only be optional integrations — the app must run free and offline on the user's Mac.
- Never invent, interpolate or substitute missing statistics; return MISSING_DATA — trust over completeness.
- Canonical audit rules live in `backend/app/domain/audit.py`; keep `src/features/audit/rules.ts` in sync for local mode (truth/labour audits are backend-only because those records do not exist locally).
- AI access only via `src/services/aiProvider.ts`; never fabricate AI output — no provider coupling in UI.
- Simulation, economics, audit and receipt logic live in `src/features/*` as pure functions, never inside components.
- Domain types live in `src/types/lifespan.ts`; all mock data in `src/mock/` and must be labelled as prototype.
- No auth, no cloud, no Docker; backend binds 127.0.0.1 with localhost-only CORS (local-first requirement).
