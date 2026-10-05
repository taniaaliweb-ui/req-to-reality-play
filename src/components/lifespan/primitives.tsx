import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { AuditOutcome, FactType, Level, Reliability } from "@/types/lifespan";
import { useLifespan } from "@/hooks/useLifespan";
import { FlaskConical } from "lucide-react";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-6 border-b border-border pb-4">
      <div>
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="text-3xl font-medium">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  );
}

export function MockBanner({ children }: { children?: ReactNode }) {
  const { db } = useLifespan();
  if (!db.settings.showMockBanners) return null;
  return (
    <div className="hatch-mock mb-5 flex items-center gap-2 rounded-sm border border-mock/40 px-3 py-2 text-xs">
      <FlaskConical className="h-3.5 w-3.5 text-mock" />
      <span className="font-mono font-semibold uppercase tracking-wider text-mock">Prototype data</span>
      <span className="text-foreground/80">{children ?? "All values on this page are mock/illustrative and unverified."}</span>
    </div>
  );
}

const typeStyles: Record<FactType, string> = {
  FACT: "border-fact/40 bg-fact-soft text-fact",
  ESTIMATE: "border-estimate/40 bg-estimate-soft text-estimate",
  ASSUMPTION: "border-assumption/50 bg-assumption-soft text-assumption border-dashed",
  DERIVED: "border-derived/40 bg-derived-soft text-derived",
};
export const FactTypeChip = ({ t }: { t: FactType }) => <span className={cn("chip", typeStyles[t])}>{t}</span>;

const confStyles: Record<Level, string> = {
  high: "text-pass border-pass/40",
  medium: "text-warn border-warn/40",
  low: "text-fail border-fail/40",
};
export const ConfidenceChip = ({ c }: { c: Level }) => <span className={cn("chip bg-card", confStyles[c])}>{c}</span>;

const relStyles: Record<Reliability, string> = {
  Primary: "bg-fact text-primary-foreground border-fact",
  Strong: "bg-fact-soft text-fact border-fact/40",
  Moderate: "bg-secondary text-muted-foreground border-border",
  Weak: "bg-assumption-soft text-assumption border-assumption/40",
};
export const ReliabilityChip = ({ r }: { r: Reliability }) => <span className={cn("chip", relStyles[r])}>{r}</span>;

const outStyles: Record<AuditOutcome, string> = {
  PASS: "bg-pass text-primary-foreground border-pass",
  WARNING: "bg-warn text-primary-foreground border-warn",
  FAIL: "bg-fail text-primary-foreground border-fail",
};
export const OutcomeChip = ({ o }: { o: AuditOutcome }) => <span className={cn("chip", outStyles[o])}>{o}</span>;

export const SimChip = () => <span className="chip border-sim/40 bg-sim-soft text-sim">Simulation</span>;
export const StoryChip = () => <span className="chip border-primary/30 bg-accent text-primary">Story</span>;

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "warn" | "fail" | undefined }) {
  return (
    <div className="panel px-4 py-3">
      <div className="eyebrow">{label}</div>
      <div className={cn("data mt-1 text-2xl", tone === "warn" && "text-warn", tone === "fail" && "text-fail")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function Slider({ label, value, onChange, hint }: { label: string; value: number; onChange: (n: number) => void; hint?: string }) {
  return (
    <label className="block">
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-medium">{label}</span>
        <span className="data text-muted-foreground">{value}</span>
      </div>
      <input type="range" min={0} max={100} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-primary" />
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </label>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

export function EmptyEpisode() {
  return <div className="panel p-8 text-center text-muted-foreground">No active episode. Create or select one from Episodes.</div>;
}
