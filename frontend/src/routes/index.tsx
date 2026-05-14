import { createFileRoute } from "@tanstack/react-router";
import { useStatus } from "@/hooks/use-status";
import { Header } from "@/components/crisis/Header";
import { VideoFeed } from "@/components/crisis/VideoFeed";
import { AlertsPanel } from "@/components/crisis/AlertsPanel";
import { AgentTimeline } from "@/components/crisis/AgentTimeline";
import { MetricsStrip } from "@/components/crisis/MetricsStrip";
import { IntegrityPanel } from "@/components/crisis/IntegrityPanel";
import { DemoPanel } from "@/components/crisis/DemoPanel";

export const Route = createFileRoute("/")({
  component: CommandCenter,
});

function CommandCenter() {
  const { data, connected } = useStatus();

  return (
    <div className="min-h-screen">
      <Header status={data.status} connected={connected} />

      <main className="mx-auto max-w-[1600px] space-y-4 px-6 py-6">
        <MetricsStrip metrics={data.metrics} status={data.status} />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <VideoFeed frame={data.frame} status={data.status} />
          </div>
          <div className="lg:col-span-2 space-y-4">
            <AlertsPanel alerts={data.alerts} />
            {/* Aegis integrity panel — collapsible side panel */}
            <IntegrityPanel
              tamperAlerts={data.tamper_alerts}
              activeCameras={data.active_cameras}
            />
          </div>
        </div>

        <DemoPanel />

        <AgentTimeline logs={data.logs} />

        <footer className="pt-4 text-center font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground/60">
          SecureEye · Tamper-Resistant Surveillance & AI Crisis Response · for authorized operators only
        </footer>
      </main>
    </div>
  );
}
