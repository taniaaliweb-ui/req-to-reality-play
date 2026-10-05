import { useState } from "react";
import { ApiError, lifespanApi } from "@/services/lifespanApi";
import type { EngineResult, VerifiedEconomics } from "@/types/lifespan";
import { Field } from "./primitives";
import { cn } from "@/lib/utils";

const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Request failed.");
const COUNTRIES = [["IND", "India · INR"], ["ARE", "United Arab Emirates · AED"], ["USA", "United States · USD"]] as const;

function ResultBox({ r, onSaved }: { r: EngineResult; onSaved?: string }) {
  return (
    <div className={cn("mt-3 rounded-sm border p-2 text-xs", r.status === "OK" ? "border-derived/50" : "border-warn/60")}>
      <div className="flex items-center gap-2"><span className={cn("chip", r.status === "OK" ? "border-derived text-derived" : "border-warn text-warn")}>{r.status === "OK" ? "DERIVED" : r.status}</span><span className="data text-muted-foreground">{r.formulaVersion} · engine {r.engineVersion}</span></div>
      {r.status === "OK" ? (
        <>
          <div className="data mt-1 text-lg">{Number(r.display).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</div>
          <div className="data break-all text-[10px] text-muted-foreground">full precision: {r.result}</div>
          <div className="mt-1">{r.labels.join(" ")}</div>
          <div className="data mt-1 text-muted-foreground">{r.formula}</div>
          <ul className="mt-1 text-muted-foreground">
            {r.observations.map((o) => <li key={o.id} className="data">{o.indicatorCode} {o.countryCode} {o.year} = {o.value} · World Bank · retrieved {o.retrievedAt.slice(0, 10)}</li>)}
          </ul>
        </>
      ) : (
        <div className="mt-1">{r.missing.length ? <>Missing data — not invented, not interpolated: <b>{r.missing.join(", ")}</b>. Fetch it on the Data Sources page; if the provider has no value, it stays missing.</> : r.errors.join("; ")}</div>
      )}
      {onSaved && <div className="mt-1 text-pass">Saved as derived fact {onSaved} with full lineage (see Fact Ledger).</div>}
    </div>
  );
}

export function InflationCalculator({ episodeId, onSaved }: { episodeId?: string; onSaved: () => Promise<void> }) {
  const [f, setF] = useState({ country: "IND", amount: "50000", sourceYear: 1995, targetYear: 2010 });
  const [r, setR] = useState<EngineResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (save: boolean) => {
    setErr(null);
    try {
      const res = await lifespanApi.truth.inflationAdjust({ ...f, episodeId, save });
      setR(res);
      if (save && res.factId) await onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : errMsg(e));
    }
  };
  return (
    <div className="panel p-3 text-xs">
      <div className="font-medium">Inflation adjustment</div>
      <div className="mb-2 text-muted-foreground">Same country only. amount × CPI(target) ÷ CPI(source).</div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Country"><select aria-label="Inflation country" className="input" value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })}>{COUNTRIES.map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></Field>
        <Field label="Amount (local currency)"><input aria-label="Inflation amount" className="input data" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label="Amount's year"><input aria-label="Source year" type="number" className="input data" value={f.sourceYear} onChange={(e) => setF({ ...f, sourceYear: Number(e.target.value) })} /></Field>
        <Field label="Express in year"><input aria-label="Target year" type="number" className="input data" value={f.targetYear} onChange={(e) => setF({ ...f, targetYear: Number(e.target.value) })} /></Field>
      </div>
      <div className="mt-2 flex gap-2"><button className="btn" onClick={() => void run(false)}>Calculate</button><button className="btn-primary" disabled={!episodeId} onClick={() => void run(true)}>Calculate &amp; save as derived fact</button></div>
      {err && <div className="mt-2 text-fail">{err}</div>}
      {r && <ResultBox r={r} onSaved={r.factId} />}
    </div>
  );
}

export function CurrencyCalculator({ episodeId, onSaved }: { episodeId?: string; onSaved: () => Promise<void> }) {
  const [f, setF] = useState({ amount: "500000", year: 1998, fromCountry: "IND", toCountry: "USA" });
  const [r, setR] = useState<EngineResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async (save: boolean) => {
    setErr(null);
    try {
      const res = await lifespanApi.truth.currencyConvert({ ...f, episodeId, save });
      setR(res);
      if (save && res.factId) await onSaved();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : errMsg(e));
    }
  };
  return (
    <div className="panel p-3 text-xs">
      <div className="font-medium">Historical currency conversion</div>
      <div className="mb-2 text-muted-foreground">Annual-average official rates, bridged through USD. Not a daily rate.</div>
      <div className="grid grid-cols-2 gap-2">
        <Field label="From"><select aria-label="From currency" className="input" value={f.fromCountry} onChange={(e) => setF({ ...f, fromCountry: e.target.value })}>{COUNTRIES.map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></Field>
        <Field label="To"><select aria-label="To currency" className="input" value={f.toCountry} onChange={(e) => setF({ ...f, toCountry: e.target.value })}>{COUNTRIES.map(([c, l]) => <option key={c} value={c}>{l}</option>)}</select></Field>
        <Field label="Amount"><input aria-label="FX amount" className="input data" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        <Field label="Year (annual average)"><input aria-label="FX year" type="number" className="input data" value={f.year} onChange={(e) => setF({ ...f, year: Number(e.target.value) })} /></Field>
      </div>
      <div className="mt-2 flex gap-2"><button className="btn" onClick={() => void run(false)}>Convert</button><button className="btn-primary" disabled={!episodeId} onClick={() => void run(true)}>Convert &amp; save as derived fact</button></div>
      {err && <div className="mt-2 text-fail">{err}</div>}
      {r && <ResultBox r={r} onSaved={r.factId} />}
    </div>
  );
}

export function VerifiedLedger({ episodeId }: { episodeId: string }) {
  const [baseYear, setBaseYear] = useState(2010);
  const [v, setV] = useState<VerifiedEconomics | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const load = async () => {
    setErr(null);
    try {
      setV(await lifespanApi.truth.verifiedEconomics(episodeId, baseYear));
    } catch (e) {
      setErr(errMsg(e));
    }
  };
  const fmt = (x: string | null) => (x === null ? null : Math.round(Number(x)).toLocaleString("en-IN"));
  return (
    <section className="panel mb-4 p-4">
      <div className="flex items-center gap-3">
        <div className="eyebrow">Verified economic data</div>
        <label className="ml-auto flex items-center gap-1.5 text-xs">Base year <input aria-label="Base year" type="number" className="input data w-20 py-1" value={baseYear} onChange={(e) => setBaseYear(Number(e.target.value))} /></label>
        <button className="btn" onClick={() => void load()}>Recalculate verified fields</button>
      </div>
      {err && <div className="mt-2 text-xs text-fail">{err}</div>}
      {v && (
        <>
          <p className="mt-2 text-xs text-muted-foreground">{v.note} Engine {v.engineVersion} · {v.formulas.join(", ")}.</p>
          <div className="mt-2 max-h-80 overflow-auto">
            <table className="tbl data whitespace-nowrap text-[12px]">
              <thead><tr><th>Year</th><th className="text-right">Household nominal <span className="text-mock">(PROTOTYPE)</span></th><th className="text-right">Inflation-adjusted, {v.baseYear} prices <span className="text-derived">(DERIVED)</span></th><th className="text-right">Historical USD, annual-avg FX <span className="text-derived">(DERIVED)</span></th><th>Missing inputs</th></tr></thead>
              <tbody>
                {v.years.map((y) => (
                  <tr key={y.year}>
                    <td>{y.year}</td>
                    <td className="text-right hatch-mock">{fmt(y.nominalHousehold)} {y.currency}</td>
                    <td className="text-right">{fmt(y.real) ?? <span className="text-warn">missing</span>}</td>
                    <td className="text-right">{fmt(y.usd) ?? <span className="text-warn">missing</span>}</td>
                    <td className="text-[11px] text-muted-foreground">{y.missing.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
