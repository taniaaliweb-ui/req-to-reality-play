import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { PageHeader } from "@/components/lifespan/primitives";
import { BackendOnly, ErrorLine, useBackend } from "@/components/lifespan/sim";
import { lifespanApi } from "@/services/lifespanApi";
import { pageHead } from "@/lib/seo";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/model-validation")({
  head: pageHead("Model Validation", "Inspect the LifeSpan simulation model: engine versions, every prior, empirical inputs, assumptions, deterministic rules, methods and known limitations."),
  component: ModelValidation,
});

const CLS_TONE: Record<string, string> = { EMPIRICAL: "text-pass", DERIVED: "text-pass", USER_ASSUMPTION: "text-warn", PROVISIONAL_MODEL_PRIOR: "text-mock", DETERMINISTIC_ACCOUNTING_RULE: "text-muted-foreground" };

function ModelValidation() {
  const { activeId } = useLifespan();
  const { data, error } = useBackend(() => lifespanApi.sim.validation(activeId), [activeId]);
  const [filter, setFilter] = useState<string>("ALL");
  const priors = (data?.activePriors ?? []).filter((p) => filter === "ALL" || p.classification === filter);
  return (
    <>
      <PageHeader eyebrow="System · Inspection" title="Model Validation" description="Everything the simulation uses, in one report — so the model can be inspected before any external AI gets access." />
      <BackendOnly>
        {error && <ErrorLine msg={error} />}
        {data && (
          <div className="space-y-6">
            <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {[["Simulation engine", data.simulationEngineVersion], ["Economic engine", data.economicEngineVersion], ["Prior registry", data.priorRegistryVersion],
                ["Hidden-constant scan", `${data.constantScan.status} · ${data.constantScan.unregistered.length} unregistered · ${data.constantScan.taggedCount} tagged rules`]].map(([k, v]) => (
                <div key={k} className="panel p-3"><div className="field-label">{k}</div><div className={cn("data text-sm", k === "Hidden-constant scan" && (data.constantScan.status === "PASS" ? "text-pass" : "text-fail"))}>{v}</div></div>
              ))}
            </section>
            {data.constantScan.unregistered.length > 0 && <section className="panel p-3 text-xs text-fail">{data.constantScan.unregistered.map((u) => <div key={`${u.file}${u.line}`}>{u.file}:{u.line} {u.value} — {u.code}</div>)}</section>}

            <section className="panel">
              <div className="panel-header text-sm"><span>All active priors ({data.activePriors.length})</span>
                <select className="input text-xs" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="ALL">all classifications</option>{data.classifications.map((c) => <option key={c}>{c}</option>)}</select></div>
              <table className="w-full text-xs"><thead className="text-left text-muted-foreground"><tr><th className="p-2">Id</th><th>Name</th><th>Classification</th><th>Parameters</th><th>Provenance</th></tr></thead>
                <tbody>{priors.map((p) => (
                  <tr key={p.id} className="border-t border-border align-top"><td className="data p-2">{p.id}{!p.enabled && " (disabled)"}</td><td>{p.name}</td>
                    <td className={CLS_TONE[p.classification ?? ""]}>{p.classification}</td><td className="data max-w-md break-all text-[10px]">{JSON.stringify(p.parameter)}</td><td className="text-muted-foreground">{p.provenance}</td></tr>
                ))}</tbody></table>
            </section>

            <section className="grid gap-4 lg:grid-cols-2">
              <div className="panel p-3 text-xs"><div className="mb-2 text-sm font-medium">Empirical model inputs (from the frozen snapshot)</div>
                {data.empiricalInputs.map((e) => <div key={e.input} className="border-t border-border py-1"><b className="data">{e.input}</b> → {e.usedBy}<div className="text-muted-foreground">{e.source} · {e.transformation}</div></div>)}
                {data.episode?.snapshotInputs && <div className="mt-2 border-t border-border pt-2"><div className="field-label">Active episode · {data.episode.snapshotInputs.snapshot.label}</div>
                  <div>Life tables: {Object.entries(data.episode.snapshotInputs.lifeTable).map(([k, v]) => `${k} ${v.first}–${v.last} (${v.years} yrs)`).join("; ") || <span className="text-warn">none — mortality uses broad fallback</span>}</div>
                  <div>CPI: {data.episode.snapshotInputs.cpiCountries.join(", ") || "none"} · FX: {data.episode.snapshotInputs.fxCountries.join(", ") || "none"} · wage anchors: {data.episode.snapshotInputs.wageAnchors}</div></div>}
                {data.episode?.canonical && <div className="mt-2">Canonical life mortality methods by year: <span className="data">{JSON.stringify(data.episode.canonical.mortalityMethodYears)}</span></div>}
              </div>
              <div className="panel p-3 text-xs"><div className="mb-2 text-sm font-medium">Assumption-based parameters (active episode snapshot)</div>
                {data.assumptionParameters.length === 0 && <div className="text-muted-foreground">No snapshot assumptions (or no finalized snapshot).</div>}
                {data.assumptionParameters.map((a) => <div key={a.id} className="border-t border-border py-1"><span className="data">{a.id}</span> · {a.domain} · {a.claim} <span className="data">{a.value} {a.unit}</span> <span className="text-muted-foreground">{a.years.filter(Boolean).join("–")}</span></div>)}
              </div>
            </section>

            <section className="panel p-3 text-xs"><div className="mb-2 text-sm font-medium">Hard-coded deterministic rules</div>
              {data.deterministicRules.map((r) => <div key={r.id} className="border-t border-border py-1"><b className="data">{r.id}</b> — {r.description}
                {r.occurrences.length > 0 && <span className="data ml-1 text-[10px] text-muted-foreground">({r.occurrences.map((o) => `${o.file}:${o.line}`).join(", ")})</span>}
                {r.parameter && <span className="data ml-1 text-[10px]">{JSON.stringify(r.parameter)}</span>}</div>)}
            </section>

            <section className="grid gap-4 lg:grid-cols-3">
              {([["mortality", "Mortality methodology"], ["wage", "Wage methodology"], ["financialReconciliation", "Financial reconciliation"]] as const).map(([k, t]) => (
                <div key={k} className="panel p-3 text-xs"><div className="mb-2 text-sm font-medium">{t}</div><ol className="list-decimal space-y-1 pl-4">{(data.methodology[k] ?? []).map((x) => <li key={x}>{x}</li>)}</ol></div>
              ))}
            </section>

            <section className="panel p-3 text-xs"><div className="mb-2 text-sm font-medium">Known limitations</div><ul className="list-disc space-y-1 pl-4">{data.knownLimitations.map((x) => <li key={x}>{x}</li>)}</ul>
              <div className="mt-2 text-muted-foreground">{data.note}</div></section>
          </div>
        )}
      </BackendOnly>
    </>
  );
}
