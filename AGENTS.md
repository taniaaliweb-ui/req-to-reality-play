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
- UI reads/writes data only through `src/services/lifespanApi.ts` (local localStorage now, HTTP backend later) — keeps the backend swappable.
- AI access only via `src/services/aiProvider.ts`; never fabricate AI output — no provider coupling in UI.
- Simulation, economics, audit and receipt logic live in `src/features/*` as pure functions, never inside components.
- Domain types live in `src/types/lifespan.ts`; all mock data in `src/mock/` and must be labelled as prototype.
- No auth, no cloud, no Docker required for local dev (local-first requirement).
