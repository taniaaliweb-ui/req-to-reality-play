import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useLifespan } from "@/hooks/useLifespan";
import { PageHeader } from "@/components/lifespan/primitives";
import { getIntegrations } from "@/services/integrations";
import { API_URL, lifespanApi, type HealthStatus } from "@/services/lifespanApi";
import { aiProvider } from "@/services/aiProvider";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";
import type { ProviderInfo } from "@/types/lifespan";

export const Route = createFileRoute("/status")({
  head: pageHead("System Status", "Honest connection status for backend, database, AI workers, Hermes and MCP."),
  component: Status,
});

function Status() {
  const { db, mode } = useLifespan();
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  useEffect(() => {
    let alive = true;
    const check = () =>
      lifespanApi.health().then((h) => {
        if (!alive) return;
        setHealth(h);
        if (h.online) lifespanApi.truth.providers(true).then((p) => alive && setProviders(p)).catch(() => alive && setProviders([]));
      });
    void check();
    const t = setInterval(check, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  const items = getIntegrations(mode, API_URL, db.settings.hermesUrl, health, providers);
  return (
    <>
      <PageHeader eyebrow="System" title="System Status" description="Checked live against the backend health endpoint. Future systems are never marked online." />
      <div className="panel divide-y divide-border">
        {items.map((i) => (
          <div key={i.name} className="flex items-center gap-4 px-4 py-3">
            <span className={cn("h-2.5 w-2.5 rounded-full", i.status === "online" ? "bg-pass" : i.status === "offline" ? "bg-fail" : i.status === "local" ? "bg-fact" : i.status === "disabled" ? "bg-border" : "bg-warn")} />
            <div className="w-48 font-medium">{i.name}</div>
            <div className="flex-1 text-sm text-muted-foreground">{i.description}</div>
            {i.endpoint && <code className="data text-xs text-muted-foreground">{i.endpoint}</code>}
            <span className={cn("chip w-44 justify-center border-border", i.status === "online" && "border-pass text-pass", i.status === "offline" && "border-fail text-fail")}>{i.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-6 grid grid-cols-3 gap-3 text-xs">
        <div className="panel p-3"><div className="eyebrow">Data mode</div><div className="data mt-1">{mode}</div></div>
        <div className="panel p-3"><div className="eyebrow">AI provider</div><div className="data mt-1">{aiProvider.id} · configured: {String(aiProvider.configured)}</div></div>
        <div className="panel p-3"><div className="eyebrow">Records loaded</div><div className="data mt-1">{db.facts.length} facts · {db.timeline.length} events · {db.economics.length} econ-years</div></div>
      </div>
    </>
  );
}
