import { ExportPanel, Receipt2Panel } from "@/components/lifespan/product";
import type { ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Printer } from "lucide-react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, FactTypeChip, MockBanner, PageHeader } from "@/components/lifespan/primitives";
import { deriveReceipt } from "@/features/receipt/derive";
import { formatMoney } from "@/features/economics/calc";
import { CLASS_LABELS } from "@/lib/defaults";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/receipt")({
  head: pageHead("Life Receipt", "A printable, document-style summary of a simulated life."),
  component: Receipt,
});

function Receipt() {
  const { db, active } = useLifespan();
  const { facts } = useActiveRecords();
  if (!active) return <EmptyEpisode />;
  const r = deriveReceipt(db, active.id);
  if (!r) return null;
  const m = (n: number) => formatMoney(n, r.currency);
  const Row = ({ k, v }: { k: string; v: ReactNode }) => <div className="flex justify-between gap-6 py-0.5"><span className="text-muted-foreground">{k}</span><span className="text-right">{v}</span></div>;
  const List = ({ title, items }: { title: string; items: string[] }) => (
    <div className="py-2"><div className="mb-1 text-muted-foreground">{title}</div>{items.length ? items.map((i) => <div key={i}>· {i}</div>) : <div>—</div>}</div>
  );
  const Rule = () => <div className="my-2 border-t border-dashed border-foreground/30" />;
  return (
    <>
      <PageHeader eyebrow="Pipeline · 11" title="Life Receipt" description="Derived deterministically from the timeline and economic ledger." actions={<button className="btn" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</button>} />
      <Receipt2Panel eid={active.id} />
      <ExportPanel eid={active.id} />
      <h2 className="mb-2 text-sm font-medium text-muted-foreground">Prototype receipt (timeline + economic ledger)</h2>
      {active.isMock && <MockBanner>This receipt is computed from mock data. Do not cite any figure.</MockBanner>}
      <div className="grid grid-cols-[440px_1fr] gap-8">
        <div className="receipt px-7 pb-10 pt-7">
          <div className="text-center">
            <div className="font-serif text-2xl tracking-[0.2em]">LIFE RECEIPT</div>
            <div className="text-[11px] text-muted-foreground">{active.character.name}</div>
            <div className="text-[11px] text-muted-foreground">{active.id}</div>
          </div>
          <Rule />
          <Row k="Born" v={r.born} /><Row k="Died" v={r.died || "—"} /><Row k="Age" v={r.age || "—"} />
          <Row k="Countries lived in" v={r.countries.join(", ")} />
          <Rule />
          <Row k="Education" v={r.education} />
          <div className="py-1"><div className="text-muted-foreground">Career</div><div>{r.career || "—"}</div></div>
          <Row k="Years working" v={r.yearsWorking} /><Row k="Years retired" v={r.yearsRetired} />
          <Rule />
          <Row k="Lifetime earnings (nominal)" v={m(r.lifetimeNominal)} />
          <Row k="Lifetime earnings (real)" v={m(r.lifetimeReal)} />
          <Row k="Taxes" v="not modelled" />
          <Row k="Housing spent" v={m(r.housingSpent)} />
          <Row k="Education spent" v={m(r.educationSpent)} />
          <Row k="Healthcare spent" v={m(r.healthcareSpent)} />
          <Row k="Children" v={r.children} />
          <Row k="Peak net worth" v={m(r.peakNetWorth)} />
          <Row k="Net worth at death" v={m(r.netWorthAtDeath)} />
          <Rule />
          <List title="Major turning points" items={r.turningPoints} />
          <List title="Major losses" items={r.losses} />
          <List title="Major achievements" items={r.achievements} />
          <Rule />
          <div className="text-muted-foreground">Social mobility</div>
          <div className="flex items-center justify-between text-base"><span>{CLASS_LABELS[r.startingClass]}</span><span>→</span><span className="font-semibold">{CLASS_LABELS[r.endingClass]}</span></div>
          <Rule />
          <div className="text-center text-[11px] text-muted-foreground">TOTAL: ONE LIFE · NO REFUNDS</div>
        </div>
        <section>
          <h2 className="mb-3 text-xl">Sources & uncertainty</h2>
          <div className="panel overflow-hidden">
            <table className="tbl">
              <thead><tr><th>Type</th><th>Metric</th><th>Source</th><th>Confidence</th></tr></thead>
              <tbody>{facts.map((f) => <tr key={f.id}><td><FactTypeChip t={f.factType} /></td><td>{f.metric}</td><td className="data text-xs">{f.sourceId ?? "—"}</td><td className="text-xs">{f.confidence}</td></tr>)}</tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Ending class is a placeholder heuristic on final net worth; a sourced class model will replace it.</p>
        </section>
      </div>
    </>
  );
}
