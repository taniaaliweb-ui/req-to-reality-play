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
- Canonical audit rules live in `backend/app/domain/audit.py`; keep `src/features/audit/rules.ts` in sync for local mode.
- AI access only via `src/services/aiProvider.ts`; never fabricate AI output — no provider coupling in UI.
- Simulation, economics, audit and receipt logic live in `src/features/*` as pure functions, never inside components.
- Domain types live in `src/types/lifespan.ts`; all mock data in `src/mock/` and must be labelled as prototype.
- No auth, no cloud, no Docker; backend binds 127.0.0.1 with localhost-only CORS (local-first requirement).
