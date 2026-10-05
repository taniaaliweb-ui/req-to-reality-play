import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { ConfidenceChip, EmptyEpisode, FactTypeChip, Field, MockBanner, PageHeader } from "@/components/lifespan/primitives";
import { RESEARCH_TEMPLATE } from "@/features/episodes/scaffold";
import type { Fact, FactStatus, FactType, Level, ResearchCategory } from "@/types/lifespan";
import { newId } from "@/services/lifespanApi";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/facts")({
  head: pageHead("Fact Ledger", "Every historical and statistical value, typed as fact, estimate, assumption or derived."),
  component: Facts,
});

const TYPES: FactType[] = ["FACT", "ESTIMATE", "ASSUMPTION", "DERIVED"];
const CATS = Object.keys(RESEARCH_TEMPLATE) as ResearchCategory[];

function Facts() {
  const { active, db, mutate } = useLifespan();
  const { facts } = useActiveRecords();
  const [q, setQ] = useState({ country: "", year: "", category: "", confidence: "", type: "", unresolved: false });
  const [edit, setEdit] = useState<Fact | null>(null);
  const rows = useMemo(() => facts.filter((f) =>
    (!q.country || f.country === q.country) &&
    (!q.year || (Number(q.year) >= f.yearStart && Number(q.year) <= f.yearEnd)) &&
    (!q.category || f.category === q.category) &&
    (!q.confidence || f.confidence === q.confidence) &&
    (!q.type || f.factType === q.type) &&
    (!q.unresolved || f.status === "unresolved" || f.status === "unverified")), [facts, q]);
  if (!active) return <EmptyEpisode />;
  const countries = Array.from(new Set(facts.map((f) => f.country)));
  const counts = TYPES.map((t) => [t, facts.filter((f) => f.factType === t).length] as const);

  const newFact = (): Fact => ({ id: "", createdAt: "", updatedAt: "", episodeId: active.id, category: "Economy", metric: "", value: "", unit: "", country: active.character.country, region: active.character.region, yearStart: active.character.birthYear, yearEnd: active.character.birthYear, sourceId: null, confidence: "low", factType: "ASSUMPTION", notes: "", status: "unresolved" });
  const save = () => {
    if (!edit) return;
    const now = new Date().toISOString();
    mutate((d) => edit.id
      ? { ...d, facts: d.facts.map((f) => (f.id === edit.id ? { ...edit, updatedAt: now } : f)) }
      : { ...d, facts: [...d.facts, { ...edit, id: newId("F"), createdAt: now, updatedAt: now }] }, { kind: edit.factType === "ASSUMPTION" ? "assumption" : "fact", text: `${edit.id ? "Updated" : "Added"} ${edit.factType}: ${edit.metric}` });
    setEdit(null);
  };
  const del = () => { if (edit?.id) mutate((d) => ({ ...d, facts: d.facts.filter((f) => f.id !== edit.id) })); setEdit(null); };

  return (
    <>
      <PageHeader eyebrow="Pipeline · 5" title="Fact Ledger" description="Facts, estimates, assumptions and derived values are never silently mixed." actions={<button className="btn-primary" onClick={() => setEdit(newFact())}><Plus className="h-4 w-4" /> Add record</button>} />
      {active.isMock && <MockBanner>All values in the demo ledger are mock. “verified” status here is illustrative.</MockBanner>}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex gap-2">{counts.map(([t, n]) => <button key={t} onClick={() => setQ({ ...q, type: q.type === t ? "" : t })} className={cn("flex items-center gap-1.5 rounded-sm border px-2 py-1", q.type === t ? "border-foreground" : "border-transparent")}><FactTypeChip t={t} /><span className="data text-xs">{n}</span></button>)}</div>
        <div className="ml-auto flex flex-wrap items-end gap-2">
          <select className="input w-32" value={q.country} onChange={(e) => setQ({ ...q, country: e.target.value })}><option value="">All countries</option>{countries.map((c) => <option key={c}>{c}</option>)}</select>
          <input className="input data w-24" placeholder="Year" value={q.year} onChange={(e) => setQ({ ...q, year: e.target.value })} />
          <select className="input w-40" value={q.category} onChange={(e) => setQ({ ...q, category: e.target.value })}><option value="">All categories</option>{CATS.map((c) => <option key={c}>{c}</option>)}</select>
          <select className="input w-32" value={q.confidence} onChange={(e) => setQ({ ...q, confidence: e.target.value })}><option value="">Any confidence</option>{["high", "medium", "low"].map((c) => <option key={c}>{c}</option>)}</select>
          <label className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={q.unresolved} onChange={(e) => setQ({ ...q, unresolved: e.target.checked })} /> Unresolved only</label>
        </div>
      </div>
      <div className="grid grid-cols-[1fr_auto] gap-6">
        <div className="panel overflow-auto">
          <table className="tbl">
            <thead><tr><th>ID</th><th>Type</th><th>Category</th><th>Metric</th><th className="text-right">Value</th><th>Place</th><th>Years</th><th>Source</th><th>Conf.</th><th>Status</th></tr></thead>
            <tbody>
              {rows.map((f) => (
                <tr key={f.id} onClick={() => setEdit(f)} className={cn("cursor-pointer", f.factType === "ASSUMPTION" && "hatch-assumption")}>
                  <td className="data text-xs">{f.id}</td>
                  <td><FactTypeChip t={f.factType} /></td>
                  <td className="text-xs text-muted-foreground">{f.category}</td>
                  <td>{f.metric}{f.derivedFrom && <div className="text-[11px] text-derived">↳ {f.derivedFrom}</div>}</td>
                  <td className="data text-right">{f.value} <span className="text-muted-foreground text-[11px]">{f.unit}</span></td>
                  <td className="text-xs">{f.country}<div className="text-muted-foreground">{f.region}</div></td>
                  <td className="data text-xs">{f.yearStart === f.yearEnd ? f.yearStart : `${f.yearStart}–${f.yearEnd}`}</td>
                  <td className="data text-xs">{f.sourceId ?? <span className="text-fail">none</span>}</td>
                  <td><ConfidenceChip c={f.confidence} /></td>
                  <td className="text-xs">{f.status}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={10} className="py-8 text-center text-muted-foreground">No records match.</td></tr>}
            </tbody>
          </table>
        </div>
        {edit && (
          <aside className="panel w-80 p-4">
            <div className="mb-3 flex items-center justify-between"><div className="eyebrow">{edit.id || "New record"}</div><button className="btn-ghost" onClick={() => setEdit(null)}><X className="h-3.5 w-3.5" /></button></div>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <Field label="Type"><select className="input" value={edit.factType} onChange={(e) => setEdit({ ...edit, factType: e.target.value as FactType })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
                <Field label="Category"><select className="input" value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value as ResearchCategory })}>{CATS.map((t) => <option key={t}>{t}</option>)}</select></Field>
              </div>
              <Field label="Metric"><input className="input" value={edit.metric} onChange={(e) => setEdit({ ...edit, metric: e.target.value })} /></Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Value"><input className="input data" value={edit.value} onChange={(e) => setEdit({ ...edit, value: e.target.value })} /></Field>
                <Field label="Unit"><input className="input" value={edit.unit} onChange={(e) => setEdit({ ...edit, unit: e.target.value })} /></Field>
                <Field label="Country"><input className="input" value={edit.country} onChange={(e) => setEdit({ ...edit, country: e.target.value })} /></Field>
                <Field label="Region"><input className="input" value={edit.region} onChange={(e) => setEdit({ ...edit, region: e.target.value })} /></Field>
                <Field label="Year start"><input type="number" className="input data" value={edit.yearStart} onChange={(e) => setEdit({ ...edit, yearStart: Number(e.target.value) })} /></Field>
                <Field label="Year end"><input type="number" className="input data" value={edit.yearEnd} onChange={(e) => setEdit({ ...edit, yearEnd: Number(e.target.value) })} /></Field>
              </div>
              <Field label="Source"><select className="input" value={edit.sourceId ?? ""} onChange={(e) => setEdit({ ...edit, sourceId: e.target.value || null })}><option value="">— none —</option>{db.sources.map((s) => <option key={s.id} value={s.id}>{s.id} · {s.title.slice(0, 40)}</option>)}</select></Field>
              {edit.factType === "DERIVED" && <Field label="Derived from"><input className="input" value={edit.derivedFrom ?? ""} onChange={(e) => setEdit({ ...edit, derivedFrom: e.target.value })} /></Field>}
              <div className="grid grid-cols-2 gap-2">
                <Field label="Confidence"><select className="input" value={edit.confidence} onChange={(e) => setEdit({ ...edit, confidence: e.target.value as Level })}>{["high", "medium", "low"].map((t) => <option key={t}>{t}</option>)}</select></Field>
                <Field label="Status"><select className="input" value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value as FactStatus })}>{["verified", "unverified", "unresolved", "disputed"].map((t) => <option key={t}>{t}</option>)}</select></Field>
              </div>
              <Field label="Notes"><textarea className="input" rows={3} value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></Field>
              <div className="flex gap-2"><button className="btn-primary flex-1 justify-center" onClick={save}>Save</button>{edit.id && <button className="btn" onClick={del}>Delete</button>}</div>
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
