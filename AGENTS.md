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
- Life-context evidence lives in `backend/app/services/life_context.py`: one `life_observations` table discriminated by `domain` (population statistics, never individual outcomes), domain-specific validity windows and per-year temporal coverage (DIRECT/NEARBY/DERIVED/ASSUMED/MISSING) — extending evidence beyond its window without methodology is rejected, so coverage stays honest.
- A wage observation is an anchor for its own year only (`labor.wage_anchor_coverage`); stage years outside the window are unresolved — one observation must never stand in for a whole period.
- Phase 5 snapshot contents go in `snapshot_records` (typed frozen payloads); the content hash includes them only when present so pre-Phase-5 hashes stay valid.
- Evidence matching (`backend/app/services/labor.py`) is deterministic and explainable, never AI — rankings must be reproducible.
- Finalized dataset snapshots are immutable (service check + SQLite triggers + content hash); changes create a new version — future simulations must run on pinned data. Batch-altering snapshot tables drops the triggers, so recreate them in that migration.
- Core features must use only free official sources or local code; paid or AI services may only be optional integrations — the app must run free and offline on the user's Mac.
- Never invent, interpolate or substitute missing statistics; return MISSING_DATA — trust over completeness.
- Canonical audit rules live in `backend/app/domain/audit.py`; keep `src/features/audit/rules.ts` in sync for local mode (truth/labour audits are backend-only because those records do not exist locally).
- AI access only via `src/services/aiProvider.ts`; never fabricate AI output — no provider coupling in UI.
- Simulation, economics, story and receipt logic for real runs lives in `backend/app/simulation/` (pure engine + rules; services in run.py/product.py); routes, MCP and React only call it.
- Domain types live in `src/types/lifespan.ts`; all mock data in `src/mock/` and must be labelled as prototype.
- No auth, no cloud, no Docker; backend binds 127.0.0.1 with localhost-only CORS (local-first requirement).
- Simulation-engine rules: `backend/app/simulation/AGENTS.md`; MCP and research-acceptance rules: `backend/app/AGENTS.md`.
