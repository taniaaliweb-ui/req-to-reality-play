# LifeSpan — Phase 4 (labour, income & dataset snapshot engine)

Research workstation for historically grounded life simulations.

```text
Browser (http://127.0.0.1:3000)
   └─ React UI ─ src/services/lifespanApi.ts ── HTTP JSON (/api/v1) ──► FastAPI backend (127.0.0.1:8000)
                                                                          └─ SQLite: backend/data/lifespan.db
```

Phase 3 adds real World Bank CPI and annual-average exchange-rate data, a deterministic economic engine, and full calculation lineage. No AI, Hermes, MCP or real life simulation is connected yet. All demo-life figures remain **PROTOTYPE DATA**.

```text
World Bank API → backend provider → external_observations (SQLite) → Fact Ledger (FACT, verified)
   → economic_engine (Decimal, versioned formula) → DERIVED fact + derived_calculations + calculation_inputs
```

---

# Running LifeSpan on an M1 Mac

### Requirements
- **Node.js** (includes npm) — https://nodejs.org (LTS)
- **Python 3** (3.10 or newer) — `python3 --version` in Terminal

No Docker, no cloud account, no API keys.

### First-time setup
Open Terminal in the LifeSpan folder and run:
```bash
./scripts/setup-macos.sh
```
This creates `backend/.venv`, installs the backend packages, and runs `npm install`.

### Start LifeSpan
```bash
./scripts/start-local.sh
```
Or double-click **`start-lifespan.command`** in Finder (it runs setup on first use).

### Open browser
http://127.0.0.1:3000

### Backend health test
http://127.0.0.1:8000/api/v1/health → `{"status":"ok","service":"lifespan-backend","database":"connected",...}`

### Stop LifeSpan
Press **Ctrl + C** in the Terminal window running LifeSpan (or close that window). Both frontend and backend stop. Your data stays in `backend/data/lifespan.db`.

---

## Components
| Part | Where | Notes |
|---|---|---|
| Frontend | `src/` (React, TanStack, Vite) | Talks to data only via `src/services/lifespanApi.ts` |
| Backend | `backend/app/` (FastAPI, Pydantic, SQLAlchemy 2) | Binds to 127.0.0.1 only; CORS allows localhost/127.0.0.1 origins only |
| Database | `backend/data/lifespan.db` (SQLite) | Git-ignored. Schema managed by Alembic (`backend/migrations/`), upgraded automatically on start |
| Tests | `backend/tests/` (pytest) | Run real server processes against a temp database |

Backend layout: `api/routers` (HTTP), `schemas` (validation), `db` (models, engine, migrations), `services` (persistence), `domain` (audit engine, receipt), `seed` (prototype demo, seeded once), `core` (config).

### Data modes
```text
VITE_LIFESPAN_DATA_MODE=backend   # canonical SQLite via backend (used by start-local.sh)
VITE_LIFESPAN_DATA_MODE=local     # Phase 1 browser storage (default when unset; debugging/preview)
VITE_LIFESPAN_API_URL=http://127.0.0.1:8000
```
In backend mode an unreachable backend shows **"LifeSpan backend unavailable"** — the app never silently falls back to browser storage.

#### Truth + economic engine (Phase 3)
- **Providers** (`backend/app/providers/`): `world_bank.py` (Indicators API v2, no key), `manual.py` (values entered with a named source). Indicator registry: `FP.CPI.TOTL`, `FP.CPI.TOTL.ZG`, `PA.NUS.FCRF` — add more in `INDICATORS`.
- **Data Sources page**: fetch series for countries/years; shows retrieved vs unavailable counts. Missing years are reported, never filled in. Stored values work offline and show their retrieval date. Re-fetching keeps a revision record when a value changes.
- **Economic Ledger**: inflation adjustment (`amount × CPI_target ÷ CPI_source`, same country only) and historical currency conversion (USD bridge, annual-average rates — never shown as daily rates). "Recalculate verified fields" shows real-terms and USD columns next to the prototype nominal figures without overwriting them.
- **Fact Ledger**: click a World Bank or derived fact to see Source, Observation, Metadata and Lineage; each calculation is re-run from its stored inputs to prove it reproduces.
- **Precision**: Python `Decimal`, 28 significant digits; results stored unrounded; rounded (half-even, 2 dp) only for display. Every calculation stores `engine 1.0` and its formula version (`inflation-adjust-v1`, `fx-usd-bridge-annual-avg-v1`).
- **Audits** add: DERIVED without lineage, verified FACT without source, PROTOTYPE marked verified, missing CPI input, cross-country CPI, unlabeled FX precision, derived value edited after calculation.
- **Prepared, not populated**: `wage_observations` (no wage provider exists; nothing is inferred from GDP), `episode_dataset_snapshots` ("Pin snapshot" on Data Sources records the exact observation values an episode used).
- **Settings**: "External data access" and "World Bank provider" switches (backend-enforced).

### Labour evidence + snapshots (Phase 4)
Zero-paid core: every provider is free and official; nothing requires an API key, paid service or AI.
- **ILOSTAT** (`providers/ilostat.py`): live via the official ILO SDMX web service (`sdmx.ilo.org`, free). Registry of earnings (mean/median monthly, hourly; by sex, occupation, education, urban/rural, industry) and context series (participation, employment ratio, unemployment — stored only).
- **UAE FCSC** and **India MoSPI/PLFS**: structured CSV import of published tables (no scraping). The UAE .Stat API is checked live but returned HTTP 403 from the build environment, so it is not claimed to work.
- **Labor Data** page: fetch, filter by dimensions, CSV import with preview (rows / valid / invalid / duplicates / changed). Wage-group rows become distributions (intervals, never exact salaries).
- **Employment Evidence** page: per-life-stage economic profiles; deterministic *Evidence Match Score* (not a probability) with per-dimension reasons and year distance; accept / reject / flag / add assumption; baselines (FACT_SUPPORTED same year only, DERIVED = CPI-adjusted with lineage, ASSUMPTION with written reasoning); confidence HIGH/MEDIUM/LOW/INSUFFICIENT_DATA; prototype income shown alongside, never replaced; evidence gaps → research tasks; readiness checklist; household income structure (no invented amounts).
- **Dataset Snapshots** page: create → finalize (SHA-256 hash, SQLite triggers block edits) → new version → diff.
- Annualizing wages requires explicit assumptions (`POST /economics/annualize`); gross/net is never assumed.
- Tests: `tests/test_labor.py` (offline recorded ILOSTAT CSV in `tests/fixtures/ilo`); `LIFESPAN_LIVE_TESTS=1` adds live ILOSTAT and UAE checks.

## Phase 5 — life context evidence

- **Life Context Data** page: fetch UN World Population Prospects (official free bulk CSV, downloaded once to `backend/data/cache/`, then works offline; years after 2023 are labelled PROJECTION) and 16 World Bank context indicators (education, urbanisation, labour market, mortality, fertility, migration, remittances, ageing). Structured CSV import for India MoSPI / UAE FCSC / manual tables (education, housing, household spending, family formation, migration, pensions). Registries for historical events, policy evidence and qualitative social context (seeded entries are *unverified* until you check them).
- **Life Evidence** page: Life Evidence Matrix (13 life stages × 11 domains) with per-year coverage, cell detail (supporting evidence with Evidence Match Scores — not probabilities — candidates outside the validity window, policies, context, assumptions, gaps, research tasks), Simulation Readiness 2.0, evidence gaps → research tasks, the Assumption Register, migration-path evidence and historical events matched to life stages.
- Wage baselines now show their **wage anchor**: an observation is direct evidence only for its own year.
- Dataset snapshots also freeze life evidence, life-stage baselines, assumptions, policies, events, context, migration paths, gaps and readiness, with a readable manifest.
- Live smoke tests: `LIFESPAN_LIVE_TESTS=1 pytest -k live`. Normal tests are offline.

## Moving Phase 1 browser data
In backend mode, if this browser still has Phase 1 data, **Settings → Import Local Prototype Data** sends it to the backend (validated, IDs preserved). Existing backend records are only overwritten after confirmation. Browser data is never deleted.

### Main API (`/api/v1`)
`GET /health` · `GET /snapshot` · `POST /import` · `GET|PUT /settings` · `POST /activity`
`GET|POST /episodes` · `GET|PUT|PATCH|DELETE /episodes/{id}` · `GET|PUT /episodes/{id}/character`
`/episodes/{id}/{research-tasks|facts|timeline|economic-years|simulations|story}` (+ `/{recordId}`: GET/PUT/PATCH/DELETE)
`GET /episodes/{id}/audits` · `GET /episodes/{id}/receipt` · `/sources` (global registry)
`GET /data/providers` · `POST /data/world-bank/sync` · `POST /data/manual/observations` · `GET /data/observations`
`POST /episodes/{id}/facts/from-observations` · `POST /economics/inflation-adjust` · `POST /economics/currency-convert`
`GET /facts/{id}/lineage` · `GET /episodes/{id}/economics/verified` · `POST|GET /episodes/{id}/dataset-snapshots` · `GET /engine`
Interactive docs: http://127.0.0.1:8000/docs

### Backend tests
```bash
cd backend && .venv/bin/python -m pytest                          # offline: recorded World Bank responses in tests/fixtures/wb
cd backend && LIFESPAN_LIVE_TESTS=1 .venv/bin/python -m pytest      # also runs a live World Bank smoke test
```

## Future connections
- **Hermes** (`http://127.0.0.1:8642`): will be called by the backend; the UI only sees results through the API.
- **MCP**: the backend will expose LifeSpan data/tools over MCP so ChatGPT, Hermes and other agents share the same canonical data.
- **AI orchestration**: provider keys will live in the backend environment, behind `src/services/aiProvider.ts` on the UI side. Never in the browser.

## Epistemic rule
FACT · ESTIMATE · ASSUMPTION · DERIVED · SIMULATION · STORY are always visually distinct and never silently mixed.

## Phase 6 — simulation, story, production, export, MCP
- Simulation page: Input review (evidence vs simulation coverage) → Run Life → See why → Explore outcomes (10–500 runs as a background job) → Branch & what-if → Prior registry.
- The canonical life feeds the Timeline (SIMULATED events), Story Engine (structured local draft, no AI), Production (script editor + scenes), Life Receipt 2.0 and exports (JSON archive, CSV, Markdown, printable HTML → Print / Save as PDF).
- Local MCP server: `cd backend && python -m app.mcp_server` (stdio). System Status shows AVAILABLE only after a real handshake.
- Tests: `cd backend && python -m pytest` (Phase 6: `tests/test_simulation.py`).
