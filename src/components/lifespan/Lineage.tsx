import { useEffect, useState } from "react";
import { ApiError, lifespanApi } from "@/services/lifespanApi";
import type { LineageNode } from "@/types/lifespan";
import { FactTypeChip } from "./primitives";
import { cn } from "@/lib/utils";

/** Shows where a fact came from: source, raw observation, and (for DERIVED) the calculation and its inputs. */
export function LineagePanel({ factId, version }: { factId: string; version?: string }) {
  const [node, setNode] = useState<LineageNode | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setNode(null);
    setErr(null);
    lifespanApi.truth.lineage(factId).then((n) => alive && setNode(n)).catch((e) => alive && setErr(e instanceof ApiError ? e.message : "Could not load lineage."));
    return () => {
      alive = false;
    };
  }, [factId, version]);
  if (err) return <div className="text-xs text-muted-foreground">{err}</div>;
  if (!node) return <div className="text-xs text-muted-foreground">Loading provenance…</div>;
  return <Node n={node} depth={0} />;
}

function Node({ n, depth, role }: { n: LineageNode; depth: number; role?: string }) {
  const [tab, setTab] = useState<"source" | "observation" | "metadata">("source");
  return (
    <div className={cn("space-y-2 text-xs", depth > 0 && "border-l border-border pl-3")}>
      <div className="flex flex-wrap items-center gap-1.5">
        {role && <span className="data text-[10px] uppercase text-muted-foreground">{role}</span>}
        <FactTypeChip t={n.fact.factType} />
        {n.fact.isPrototype && <span className="chip border-mock/40 bg-mock-soft text-mock">PROTOTYPE</span>}
        {n.fact.provider && <span className="chip border-pass/50 text-pass">{n.fact.status === "verified" ? "Verified · " : ""}{n.fact.provider === "world-bank" ? "World Bank" : n.fact.provider}</span>}
        <span className="data">{n.fact.id}</span>
      </div>
      <div>{n.fact.metric}: <span className="data font-medium">{n.fact.value}</span> <span className="text-muted-foreground">{n.fact.unit}</span></div>

      {n.calculation && (
        <div className="rounded-sm border border-derived/40 p-2">
          <div className="font-medium text-derived">Calculation {n.calculation.id}</div>
          <div className="data">{n.calculation.formula}</div>
          <div className="text-muted-foreground">formula {n.calculation.formulaVersion} · engine {n.calculation.engineVersion} · {n.calculation.createdAt}</div>
          {n.calculation.labels.map((l) => <div key={l} className="text-muted-foreground">{l}</div>)}
          <div className="data mt-1 text-muted-foreground">params: {Object.entries(n.calculation.parameters).map(([k, v]) => `${k}=${String(v)}`).join(" · ")}</div>
          <div className={cn("mt-1", n.calculation.reproducible ? "text-pass" : "text-fail")}>
            {n.calculation.reproducible ? "✓ Re-computed from stored inputs: identical result" : `✗ Re-computation differs (${n.calculation.recomputedResult ?? "n/a"})`}
          </div>
          <div className="mt-2 space-y-3">{n.calculation.inputs.map((i) => <Node key={i.role + i.fact.id} n={i} role={i.role} depth={depth + 1} />)}</div>
        </div>
      )}

      {(n.source || n.observation) && (
        <div>
          <div className="mb-1 flex gap-1">
            {(["source", "observation", "metadata"] as const).filter((t) => t === "source" ? n.source : n.observation).map((t) => (
              <button key={t} className={cn("rounded-sm px-2 py-0.5 capitalize", tab === t ? "bg-foreground text-background" : "text-muted-foreground")} onClick={() => setTab(t)}>{t}</button>
            ))}
          </div>
          {tab === "source" && n.source && <div><div>{n.source.title}</div><div className="text-muted-foreground">{n.source.organization} · {n.source.reliability}</div></div>}
          {tab === "observation" && n.observation && (
            <div className="grid grid-cols-[90px_1fr] gap-y-0.5">
              <span className="text-muted-foreground">Indicator</span><span className="data">{n.observation.indicatorCode}</span>
              <span className="text-muted-foreground">Country</span><span>{n.observation.countryName}</span>
              <span className="text-muted-foreground">Year</span><span className="data">{n.observation.year}</span>
              <span className="text-muted-foreground">Raw value</span><span className="data">{n.observation.value}</span>
              <span className="text-muted-foreground">Dataset</span><span>{n.observation.dataset}</span>
              <span className="text-muted-foreground">Retrieved</span><span className="data">{n.observation.retrievedAt}</span>
              <span className="text-muted-foreground">Provider upd.</span><span className="data">{n.observation.providerLastUpdated || "—"}</span>
            </div>
          )}
          {tab === "metadata" && n.observation && (
            <div className="space-y-1">
              {n.observation.sourceOrganization && <div><span className="text-muted-foreground">Compiled by: </span>{n.observation.sourceOrganization}</div>}
              {n.observation.sourceNote && <div className="max-h-28 overflow-auto text-muted-foreground">{n.observation.sourceNote}</div>}
              <div className="text-muted-foreground">{n.observation.license}</div>
              <div className="data break-all text-muted-foreground">{n.observation.sourceUrl}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
