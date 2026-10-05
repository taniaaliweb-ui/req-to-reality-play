import { createFileRoute } from "@tanstack/react-router";
import { useLifespan } from "@/hooks/useLifespan";
import { PageHeader } from "@/components/lifespan/primitives";
import { getIntegrations } from "@/services/integrations";
import { lifespanApi } from "@/services/lifespanApi";
import { aiProvider } from "@/services/aiProvider";
import { cn } from "@/lib/utils";
import { pageHead } from "@/lib/seo";

export const Route = createFileRoute("/status")({
  head: pageHead("System Status", "Honest connection status for backend, AI workers, Hermes and MCP."),
  component: Status,
});

const LABEL = { "not-configured": "Not configured", "not-connected": "Not connected", disabled: "Disabled", local: "Local prototype", connected: "Connected" };

function Status() {
  const { db } = useLifespan();
  const items = getIntegrations(db.settings.backendUrl, db.settings.hermesUrl);
  return (
    <>
      <PageHeader eyebrow="System" title="System Status" description="No connection is faked. Everything external is offline in Phase 1." />
      <div className="panel divide-y divide-border">
        {items.map((i) => (
          <div key={i.name} className="flex items-center gap-4 px-4 py-3">
            <span className={cn("h-2.5 w-2.5 rounded-full", i.status === "connected" ? "bg-pass" : i.status === "local" ? "bg-fact" : i.status === "disabled" ? "bg-border" : "bg-warn")} />
            <div className="w-48 font-medium">{i.name}</div>
            <div className="flex-1 text-sm text-muted-foreground">{i.description}</div>
            {i.endpoint && <code className="data text-xs text-muted-foreground">{i.endpoint}</code>}
            <span className="chip w-36 justify-center border-border">{LABEL[i.status]}</span>
          </div>
        ))}
      </div>
      <div className="mt-6 grid grid-cols-3 gap-3 text-xs">
        <div className="panel p-3"><div className="eyebrow">Data API mode</div><div className="data mt-1">{lifespanApi.mode}</div></div>
        <div className="panel p-3"><div className="eyebrow">AI provider</div><div className="data mt-1">{aiProvider.id} · configured: {String(aiProvider.configured)}</div></div>
        <div className="panel p-3"><div className="eyebrow">Records</div><div className="data mt-1">{db.facts.length} facts · {db.timeline.length} events · {db.economics.length} econ-years</div></div>
      </div>
    </>
  );
}
