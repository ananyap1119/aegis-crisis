import type { Metrics, SystemStatus } from "@/lib/types";

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex-1 rounded-lg border border-border bg-card/70 px-4 py-3 backdrop-blur">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold tracking-tight text-foreground">{value}</p>
      {sub && <p className="font-mono text-[10px] text-muted-foreground/70">{sub}</p>}
    </div>
  );
}

export function MetricsStrip({ metrics, status }: { metrics: Metrics; status: SystemStatus }) {
  const conf = Math.round(metrics.confidence);
  const barColor =
    status === "ALERT" ? "bg-alert" : status === "MONITOR" ? "bg-monitor" : "bg-safe";

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      <div className="col-span-2 rounded-lg border border-border bg-card/70 px-4 py-3 backdrop-blur">
        <div className="flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            Model Confidence
          </p>
          <p className="font-mono text-xs font-semibold text-foreground">{conf}%</p>
        </div>
        <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full transition-all duration-700 ease-out ${barColor}`}
            style={{ width: `${conf}%` }}
          />
        </div>
        <p className="mt-1.5 font-mono text-[10px] text-muted-foreground/70">
          ensemble · 4 vision models
        </p>
      </div>
      <Stat label="State" value={status} sub="autonomous" />
      <Stat label="Latency" value={`${Math.round(metrics.latencyMs)}ms`} sub={`${metrics.fps.toFixed(1)} fps`} />
      <Stat label="Uptime" value={metrics.uptime} sub={`${metrics.modelsActive} models active`} />
    </div>
  );
}
