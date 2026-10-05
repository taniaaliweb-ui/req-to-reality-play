// Shared Phase 6 UI pieces. Presentation only — all simulation logic lives in the backend.
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { lifespanApi } from "@/services/lifespanApi";

const CLASS_STYLE: Record<string, string> = {
  EMPIRICAL: "border-pass/40 text-pass",
  DERIVED_FROM_EMPIRICAL: "border-primary/40 text-primary",
  ASSUMPTION_BASED: "border-warn/50 bg-assumption-soft text-foreground",
  PROVISIONAL_SYSTEM_PRIOR: "border-mock/40 bg-mock-soft text-mock",
  DETERMINISTIC: "border-border text-muted-foreground",
};
export const ProbClassChip = ({ c }: { c: string }) => <span className={cn("chip", CLASS_STYLE[c] ?? "border-border")}>{c.replaceAll("_", " ")}</span>;

const STATUS_STYLE: Record<string, string> = {
  VERIFIED: "border-pass/40 text-pass",
  "PARTIALLY VERIFIED": "border-primary/40 text-primary",
  "ASSUMPTION-COVERED": "border-warn/50 bg-assumption-soft",
  "PRIOR-COVERED": "border-mock/40 bg-mock-soft text-mock",
  MISSING: "border-fail/40 text-fail",
  BLOCKED: "border-fail bg-fail/10 text-fail",
};
export const CoverageChip = ({ s }: { s: string }) => <span className={cn("chip", STATUS_STYLE[s] ?? "border-border")}>{s}</span>;
export const SimulatedLabel = () => <span className="chip border-sim/40 bg-sim-soft text-sim">SIMULATED</span>;
export const PriorNote = () => <span className="text-[11px] italic text-mock">Provisional model prior — not externally validated</span>;

export function BackendOnly({ children }: { children: ReactNode }) {
  if (lifespanApi.mode !== "backend")
    return <div className="panel p-6 text-sm text-muted-foreground">This feature needs the local LifeSpan backend (run <code className="data">./scripts/start-local.sh</code> and open the app in backend mode). Browser-only mode holds prototype data and cannot simulate.</div>;
  return <>{children}</>;
}

/** Load-on-mount helper with explicit error state (never silent). */
export function useBackend<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    if (lifespanApi.mode !== "backend") return;
    setLoading(true);
    try {
      setData(await load());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => void refresh(), [refresh]);
  return { data, error, loading, refresh, setData };
}

export const money = (m: Record<string, string> | undefined) =>
  m && Object.keys(m).length ? Object.entries(m).map(([c, v]) => `${c} ${Math.round(Number(v)).toLocaleString()}`).join(" · ") : "—";

export function ErrorLine({ msg }: { msg: string | null }) {
  return msg ? <div className="mb-3 rounded-sm border border-fail/40 bg-fail/5 px-3 py-2 text-xs text-fail">{msg}</div> : null;
}
