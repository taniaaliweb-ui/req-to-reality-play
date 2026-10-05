# LifeSpan — Phase 2 (real local backend)

Research workstation for historically grounded life simulations.

```text
Browser (http://127.0.0.1:3000)
   └─ React UI ─ src/services/lifespanApi.ts ── HTTP JSON (/api/v1) ──► FastAPI backend (127.0.0.1:8000)
                                                                          └─ SQLite: backend/data/lifespan.db
```

No AI, Hermes, MCP, real research or real simulation is connected yet. All demo figures are **PROTOTYPE DATA**.

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

### Moving Phase 1 browser data
In backend mode, if this browser still has Phase 1 data, **Settings → Import Local Prototype Data** sends it to the backend (validated, IDs preserved). Existing backend records are only overwritten after confirmation. Browser data is never deleted.

### Main API (`/api/v1`)
`GET /health` · `GET /snapshot` · `POST /import` · `GET|PUT /settings` · `POST /activity`
`GET|POST /episodes` · `GET|PUT|PATCH|DELETE /episodes/{id}` · `GET|PUT /episodes/{id}/character`
`/episodes/{id}/{research-tasks|facts|timeline|economic-years|simulations|story}` (+ `/{recordId}`: GET/PUT/PATCH/DELETE)
`GET /episodes/{id}/audits` · `GET /episodes/{id}/receipt` · `/sources` (global registry)
Interactive docs: http://127.0.0.1:8000/docs

### Backend tests
```bash
cd backend && .venv/bin/python -m pytest
```

## Future connections
- **Hermes** (`http://127.0.0.1:8642`): will be called by the backend; the UI only sees results through the API.
- **MCP**: the backend will expose LifeSpan data/tools over MCP so ChatGPT, Hermes and other agents share the same canonical data.
- **AI orchestration**: provider keys will live in the backend environment, behind `src/services/aiProvider.ts` on the UI side. Never in the browser.

## Epistemic rule
FACT · ESTIMATE · ASSUMPTION · DERIVED · SIMULATION · STORY are always visually distinct and never silently mixed.
