import type { Character, Gender, Settlement, SocioClass } from "@/types/lifespan";
import { CLASS_LABELS, CONTROL_LABELS, TRAIT_LABELS } from "@/lib/defaults";
import { Field, Slider } from "./primitives";

type Props = { value: Character; onChange: (c: Character) => void; section?: "identity" | "family" | "traits" | "controls" | "all" | undefined };

export function CharacterForm({ value: c, onChange, section = "all" }: Props) {
  const set = (p: Partial<Character>) => onChange({ ...c, ...p });
  const show = (s: string) => section === "all" || section === s;
  return (
    <div className="space-y-6">
      {show("identity") && (
        <fieldset className="grid grid-cols-3 gap-4">
          <legend className="eyebrow col-span-3 mb-2">Identity</legend>
          <Field label="Character name / ID"><input className="input" value={c.name} onChange={(e) => set({ name: e.target.value })} /></Field>
          <Field label="Country of birth"><input className="input" value={c.country} onChange={(e) => set({ country: e.target.value })} /></Field>
          <Field label="City / region"><input className="input" value={c.region} onChange={(e) => set({ region: e.target.value })} /></Field>
          <Field label="Birth year"><input type="number" min={1900} max={2025} className="input data" value={c.birthYear} onChange={(e) => set({ birthYear: Number(e.target.value) })} /></Field>
          <Field label="Gender">
            <select className="input" value={c.gender} onChange={(e) => set({ gender: e.target.value as Gender })}>
              {["male", "female", "non-binary", "unspecified"].map((g) => <option key={g}>{g}</option>)}
            </select>
          </Field>
          <Field label="Settlement">
            <select className="input" value={c.settlement} onChange={(e) => set({ settlement: e.target.value as Settlement })}>
              {["urban", "suburban", "rural"].map((g) => <option key={g}>{g}</option>)}
            </select>
          </Field>
          <Field label="Starting socioeconomic class">
            <select className="input" value={c.startingClass} onChange={(e) => set({ startingClass: e.target.value as SocioClass })}>
              {Object.entries(CLASS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
        </fieldset>
      )}
      {show("family") && (
        <fieldset className="grid grid-cols-3 gap-4">
          <legend className="eyebrow col-span-3 mb-2">Family</legend>
          <Field label="Parents / guardians"><input type="number" min={0} max={4} className="input data" value={c.family.guardians} onChange={(e) => set({ family: { ...c.family, guardians: Number(e.target.value) } })} /></Field>
          <Field label="Siblings"><input type="number" min={0} max={15} className="input data" value={c.family.siblings} onChange={(e) => set({ family: { ...c.family, siblings: Number(e.target.value) } })} /></Field>
          <Field label="Parental income class">
            <select className="input" value={c.family.parentalIncomeClass} onChange={(e) => set({ family: { ...c.family, parentalIncomeClass: e.target.value as SocioClass } })}>
              {Object.entries(CLASS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Parental education"><input className="input" value={c.family.parentalEducation} onChange={(e) => set({ family: { ...c.family, parentalEducation: e.target.value } })} /></Field>
          <Field label="Housing situation"><input className="input" value={c.family.housing} onChange={(e) => set({ family: { ...c.family, housing: e.target.value } })} /></Field>
        </fieldset>
      )}
      {show("traits") && (
        <fieldset>
          <legend className="eyebrow mb-1">Character attributes</legend>
          <p className="mb-3 text-xs text-muted-foreground">Simulation variables only — not scientifically precise measurements.</p>
          <div className="grid grid-cols-3 gap-x-6 gap-y-4">
            {(Object.keys(TRAIT_LABELS) as (keyof typeof TRAIT_LABELS)[]).map((k) => (
              <Slider key={k} label={TRAIT_LABELS[k]} value={c.traits[k]} onChange={(n) => set({ traits: { ...c.traits, [k]: n } })} />
            ))}
          </div>
        </fieldset>
      )}
      {show("controls") && (
        <fieldset>
          <legend className="eyebrow mb-3">Simulation controls</legend>
          <div className="grid grid-cols-3 gap-x-6 gap-y-4">
            {(Object.keys(CONTROL_LABELS) as (keyof typeof CONTROL_LABELS)[]).map((k) => (
              <Slider key={k} label={CONTROL_LABELS[k]} value={c.controls[k]} onChange={(n) => set({ controls: { ...c.controls, [k]: n } })} />
            ))}
          </div>
        </fieldset>
      )}
    </div>
  );
}

export function DnaSummary({ c }: { c: Character }) {
  const lv = (n: number) => (n >= 67 ? "High" : n >= 34 ? "Medium" : "Low");
  const pressure = c.family.siblings >= 3 || ["poverty", "working"].includes(c.startingClass) ? "High" : c.startingClass === "lower-middle" ? "Moderate" : "Low";
  const rows: [string, string[]][] = [
    ["Born", [`${c.country}, ${c.birthYear}`, c.region]],
    ["Environment", [`${c.settlement.charAt(0).toUpperCase()}${c.settlement.slice(1)} ${CLASS_LABELS[c.startingClass].toLowerCase()}`]],
    ["Family", [`${c.family.guardians} parent(s)/guardian(s)`, `${c.family.siblings + 1} children`, `${pressure} financial pressure`, c.family.housing]],
    ["Traits", [`${lv(c.traits.ambition)} ambition`, `${lv(c.traits.riskTolerance)} risk tolerance`, `${lv(c.traits.resilience)} resilience`, `${lv(c.traits.migrationWillingness)} migration willingness`]],
    ["Simulation", [`${lv(c.controls.realism)} realism`, `${lv(c.controls.randomness)} randomness`, `${lv(c.controls.adversity)} adversity`]],
  ];
  return (
    <dl className="font-mono text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[110px_1fr] border-b border-dashed border-border py-2 last:border-0">
          <dt className="text-muted-foreground uppercase tracking-wider text-[11px] pt-0.5">{k}</dt>
          <dd>{v.map((x) => <div key={x}>{x}</div>)}</dd>
        </div>
      ))}
    </dl>
  );
}
