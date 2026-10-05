import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Plus, X } from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { Field, MockBanner, PageHeader, ReliabilityChip } from "@/components/lifespan/primitives";
import type { Reliability, Source, SourceType } from "@/types/lifespan";
import { newId } from "@/services/lifespanApi";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/sources")({
  head: pageHead("Source Registry", "Reusable, rated sources backing every fact in LifeSpan."),
  component: Sources,
});

const TYPES: SourceType[] = ["government", "World Bank", "UN", "OECD", "academic", "statistical agency", "newspaper", "historical archive", "industry", "other"];
const RELS: Reliability[] = ["Primary", "Strong", "Moderate", "Weak"];

const blank = (): Source => ({ id: "", createdAt: "", updatedAt: "", title: "", organization: "", url: "", publicationDate: "", accessedDate: new Date().toISOString().slice(0, 10), geoCoverage: "", timeCoverage: "", type: "government", reliability: "Moderate", notes: "" });

function Sources() {
  const { db, mutate } = useLifespan();
  const [edit, setEdit] = useState<Source | null>(null);
  const usage = (id: string) => db.facts.filter((f) => f.sourceId === id).length;
  const save = () => {
    if (!edit) return;
    const now = new Date().toISOString();
    mutate((d) => edit.id
      ? { ...d, sources: d.sources.map((s) => (s.id === edit.id ? { ...edit, updatedAt: now } : s)) }
      : { ...d, sources: [...d.sources, { ...edit, id: newId("SRC"), createdAt: now, updatedAt: now }] });
    setEdit(null);
  };
  return (
    <>
      <PageHeader eyebrow="Pipeline · 4" title="Source Registry" description="Sources are shared across all episodes and referenced by Fact Ledger records." actions={<button className="btn-primary" onClick={() => setEdit(blank())}><Plus className="h-4 w-4" /> Add source</button>} />
      <MockBanner>Sources marked [MOCK] are placeholders with example.org URLs — they are not real citations.</MockBanner>
      <div className="grid grid-cols-[1fr_auto] gap-6">
        <div className="panel overflow-auto">
          <table className="tbl">
            <thead><tr><th>ID</th><th>Title</th><th>Organization</th><th>Type</th><th>Coverage</th><th>Reliability</th><th>Used</th></tr></thead>
            <tbody>
              {db.sources.map((s) => (
                <tr key={s.id} className="cursor-pointer" onClick={() => setEdit(s)}>
                  <td className="data text-xs">{s.id}</td>
                  <td><div className="font-medium">{s.title}</div><div className="data text-[11px] text-muted-foreground">{s.url}</div></td>
                  <td>{s.organization}</td>
                  <td className="text-xs">{s.type}</td>
                  <td className="text-xs">{s.geoCoverage}<div className="data text-muted-foreground">{s.timeCoverage}</div></td>
                  <td><ReliabilityChip r={s.reliability} /></td>
                  <td className="data">{usage(s.id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {edit && (
          <aside className="panel w-80 p-4">
            <div className="mb-3 flex items-center justify-between"><div className="eyebrow">{edit.id || "New source"}</div><button className="btn-ghost" onClick={() => setEdit(null)}><X className="h-3.5 w-3.5" /></button></div>
            <div className="space-y-3">
              {(["title", "organization", "url", "publicationDate", "accessedDate", "geoCoverage", "timeCoverage"] as const).map((k) => (
                <Field key={k} label={k.replace(/([A-Z])/g, " $1")}><input className="input" value={edit[k]} onChange={(e) => setEdit({ ...edit, [k]: e.target.value })} /></Field>
              ))}
              <div className="grid grid-cols-2 gap-2">
                <Field label="Type"><select className="input" value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value as SourceType })}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
                <Field label="Reliability"><select className="input" value={edit.reliability} onChange={(e) => setEdit({ ...edit, reliability: e.target.value as Reliability })}>{RELS.map((t) => <option key={t}>{t}</option>)}</select></Field>
              </div>
              <Field label="Notes"><textarea className="input" rows={3} value={edit.notes} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></Field>
              <button className="btn-primary w-full justify-center" onClick={save}>Save source</button>
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
