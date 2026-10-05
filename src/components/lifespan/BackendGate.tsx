import type { ReactNode } from "react";
import { ServerOff, Loader2 } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { API_URL } from "@/services/lifespanApi";

/** Blocks the workspace when backend mode is on and data could not be loaded. Never falls back to browser storage. */
export function BackendGate({ children }: { children: ReactNode }) {
  const { mode, loadState, reload } = useLifespan();
  if (mode === "local" || loadState === "ready") return <>{children}</>;
  if (loadState === "loading")
    return (
      <div className="flex items-center gap-2 py-24 text-sm text-muted-foreground justify-center">
        <Loader2 className="h-4 w-4 animate-spin" /> Connecting to LifeSpan backend…
      </div>
    );
  return (
    <div className="mx-auto mt-16 max-w-lg panel p-8 text-center">
      <ServerOff className="mx-auto mb-3 h-8 w-8 text-fail" />
      <h1 className="text-2xl">{loadState === "offline" ? "LifeSpan backend unavailable" : "Could not load data"}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {loadState === "offline"
          ? <>No response from <code className="data">{API_URL}</code>. Start it with <code className="data">./scripts/start-local.sh</code>. Browser storage is not used in backend mode, so nothing is shown until the backend is reachable.</>
          : "The backend responded with an error. Details are in the browser console and backend log."}
      </p>
      <button className="btn-primary mt-5" onClick={() => void reload()}>Retry</button>
    </div>
  );
}
