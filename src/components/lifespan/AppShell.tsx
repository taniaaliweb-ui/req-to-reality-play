import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import {
  LayoutDashboard, BookOpen, Search, Table2, Library, GitBranch, PenLine, ShieldCheck, Clapperboard, Settings,
  Activity, Cpu, Database, CalendarRange, Wallet, Receipt,
  Briefcase,
  Factory,
  Lock,
} from "lucide-react";
import { useLifespan } from "@/hooks/useLifespan";
import { STAGE_LABELS, WORKFLOW_STAGES } from "@/types/lifespan";
import { cn } from "@/lib/utils";
import { BackendGate } from "./BackendGate";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/episodes", label: "Episodes", icon: BookOpen },
  { to: "/research", label: "Research", icon: Search },
  { to: "/facts", label: "Fact Ledger", icon: Table2 },
  { to: "/sources", label: "Sources", icon: Library },
  { to: "/timeline", label: "Timeline", icon: CalendarRange },
  { to: "/simulation", label: "Simulation", icon: GitBranch },
  { to: "/economics", label: "Economic Ledger", icon: Wallet },
  { to: "/evidence", label: "Employment Evidence", icon: Briefcase },
  { to: "/labor", label: "Labor Data", icon: Factory },
  { to: "/snapshots", label: "Dataset Snapshots", icon: Lock },
  { to: "/story", label: "Story", icon: PenLine },
  { to: "/audits", label: "Audits", icon: ShieldCheck },
  { to: "/production", label: "Production", icon: Clapperboard },
  { to: "/receipt", label: "Life Receipt", icon: Receipt },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
        <div className="border-b border-sidebar-border px-4 py-4">
          <div className="font-serif text-xl tracking-tight">LifeSpan</div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-sidebar-muted">Life simulation lab · v0.1</div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {NAV.map(({ to, label, icon: Icon }) => {
            const active = to === "/" ? path === "/" : path.startsWith(to);
            return (
              <Link key={to} to={to} className={cn("mb-0.5 flex items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-[13px] text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground", active && "bg-sidebar-accent text-sidebar-foreground")}>
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-sidebar-border px-2 py-3">
          <Link to="/status" className={cn("flex items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-[13px] text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground", path.startsWith("/status") && "bg-sidebar-accent text-sidebar-foreground")}>
            <Activity className="h-4 w-4" /> System Status
          </Link>
          <Link to="/data" className={cn("flex items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-[13px] text-sidebar-muted hover:bg-sidebar-accent hover:text-sidebar-foreground", path.startsWith("/data") && "bg-sidebar-accent text-sidebar-foreground")}>
            <Database className="h-4 w-4" /> Data Sources
          </Link>
          <div className="mt-2 flex items-center gap-2 px-2.5 text-[11px] text-sidebar-muted">
            <Cpu className="h-3.5 w-3.5" />
            <span>Agents: none configured</span>
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-8 py-7"><BackendGate>{children}</BackendGate></main>
      </div>
    </div>
  );
}

function TopBar() {
  const { db, active, activeId, setActiveId, saveState, saveError, mode, syncNow } = useLifespan();
  const stageIdx = active ? WORKFLOW_STAGES.indexOf(active.stage) : -1;
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur">
      <div className="flex items-center gap-4 px-8 py-2.5">
        <div className="eyebrow">Active episode</div>
        <select className="input max-w-md py-1" value={activeId} onChange={(e) => setActiveId(e.target.value)}>
          {db.episodes.map((e) => (
            <option key={e.id} value={e.id}>{e.title}</option>
          ))}
        </select>
        {active?.isMock && <span className="chip border-mock/40 bg-mock-soft text-mock">Mock</span>}
        <div className="ml-auto flex items-center gap-4 text-xs">
          <span className="text-muted-foreground">Stage: <span className="font-medium text-foreground">{active ? STAGE_LABELS[active.stage] : "—"}</span></span>
          <span className="chip border-border text-muted-foreground">{mode === "backend" ? "Backend · SQLite" : "Browser storage"}</span>
          <span className="data flex items-center gap-1.5 text-muted-foreground" title={saveError ?? undefined}>
            <span className={cn("h-1.5 w-1.5 rounded-full", saveState === "saved" ? "bg-pass" : saveState === "error" ? "bg-fail" : "bg-warn")} />
            {saveState === "saved" ? (mode === "backend" ? "Saved to backend" : "Saved locally") : saveState === "saving" ? "Saving…" : saveState === "error" ? <span className="text-fail">{saveError ?? "Save failed"}</span> : "Loading…"}
            {saveState === "error" && <button className="btn-ghost" onClick={() => void syncNow()}>Retry</button>}
          </span>
        </div>
      </div>
      <div className="flex gap-px px-8 pb-2">
        {WORKFLOW_STAGES.map((s, i) => (
          <div key={s} title={STAGE_LABELS[s]} className="flex-1">
            <div className={cn("h-1 rounded-full", i < stageIdx ? "bg-foreground/70" : i === stageIdx ? "bg-primary" : "bg-border")} />
            <div className={cn("mt-1 truncate font-mono text-[9.5px] uppercase tracking-wider", i === stageIdx ? "text-primary" : "text-muted-foreground")}>{i + 1}. {STAGE_LABELS[s]}</div>
          </div>
        ))}
      </div>
    </header>
  );
}
