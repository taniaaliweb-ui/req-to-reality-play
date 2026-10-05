import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useActiveRecords, useLifespan } from "@/hooks/useLifespan";
import { EmptyEpisode, MockBanner, PageHeader } from "@/components/lifespan/primitives";
import { formatMoney, householdIncome, netWorth, toReal, totalExpenses } from "@/features/economics/calc";
import { cn } from "@/lib/utils";
import { CurrencyCalculator, InflationCalculator, VerifiedLedger } from "@/components/lifespan/EconomicTools";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/economics")({
  head: pageHead("Economic Ledger", "Year-by-year household finances in nominal and inflation-adjusted terms."),
  component: Economics,
});

function Economics() {
  const { active, mode, reload } = useLifespan();
  const { economics } = useActiveRecords();
  const [real, setReal] = useState(false);
  if (!active) return <EmptyEpisode />;
  const base = economics[0];
  const v = (n: number, idx: number) => formatMoney(real && base ? toReal(n, idx, base.priceIndex) : n, base?.currency);
  const nws = economics.map((y) => (real && base ? toReal(netWorth(y), y.priceIndex, base.priceIndex) : netWorth(y)));
  const max = Math.max(1, ...nws);

  return (
    <>
      <PageHeader eyebrow="Pipeline · 7b" title="Economic Ledger" description="All arithmetic here is deterministic code. Inputs will come from the Fact Ledger in later phases."
        actions={<div className="flex rounded-sm border border-border p-0.5">{(["Nominal", `Prototype index (${base?.year ?? "base"})`] as const).map((l, i) => <button key={l} onClick={() => setReal(i === 1)} className={cn("rounded-sm px-3 py-1 text-xs", real === (i === 1) ? "bg-foreground text-background" : "text-muted-foreground")}>{l}</button>)}</div>} />
      {active.isMock && <MockBanner>Every figure is generated from a deterministic mock formula — not from sourced wage or price data. The price index is illustrative.</MockBanner>}
      {economics.length === 0 ? (
        <div className="panel p-8 text-center text-sm text-muted-foreground">No economic years yet. These will be computed from the Fact Ledger once the backend calculator exists.</div>
      ) : (
        <>
          <div className="panel mb-4 p-4">
            <div className="eyebrow mb-2">Net worth over lifetime</div>
            <div className="flex h-32 items-end gap-[2px]">
              {economics.map((y, i) => <div key={y.id} title={`${y.year}: ${formatMoney(nws[i] ?? 0)}`} className={cn("flex-1 rounded-t-[1px]", y.year >= 2004 && y.year < 2018 ? "bg-primary" : "bg-foreground/60")} style={{ height: `${Math.max(1, ((nws[i] ?? 0) / max) * 100)}%` }} />)}
            </div>
            <div className="data mt-1 flex justify-between text-[10px] text-muted-foreground"><span>{economics[0]?.year}</span><span>{economics.at(-1)?.year}</span></div>
          </div>
          {mode === "backend" ? (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3">
                <InflationCalculator episodeId={active.id} onSaved={reload} />
                <CurrencyCalculator episodeId={active.id} onSaved={reload} />
              </div>
              <VerifiedLedger episodeId={active.id} />
            </>
          ) : (
            <div className="panel hatch-mock mb-4 p-3 text-xs">Inflation and currency calculators use real World Bank data and run in the LifeSpan backend. Start it with ./scripts/start-local.sh.</div>
          )}
          <div className="eyebrow mb-2">Prototype ledger <span className="text-mock">— nominal amounts and the price-index toggle are demo values</span></div>
          <div className="panel max-h-[600px] overflow-auto">
            <table className="tbl data whitespace-nowrap text-[12px]">
              <thead><tr>{["Year", "Age", "Income", "Spouse", "Household", "Housing", "Food", "Education", "Health", "Transport", "Family supp.", "Debt", "Savings", "Investments", "Assets", "Liabilities", "Net worth"].map((h) => <th key={h} className="text-right first:text-left">{h}</th>)}</tr></thead>
              <tbody>
                {economics.map((y) => (
                  <tr key={y.id}>
                    <td>{y.year}</td><td className="text-right">{y.age}</td>
                    {[y.income, y.spouseIncome, householdIncome(y), y.housing, y.food, y.education, y.healthcare, y.transport, y.familySupport, y.debt, y.savings, y.investments, y.assets, y.liabilities].map((n, i) => <td key={i} className="text-right">{v(n, y.priceIndex)}</td>)}
                    <td className={cn("text-right font-semibold", netWorth(y) < 0 && "text-fail")}>{v(netWorth(y), y.priceIndex)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Total expenses in final year: {formatMoney(economics.at(-1) ? totalExpenses(economics.at(-1)!) : 0)}.</p>
        </>
      )}
    </>
  );
}
