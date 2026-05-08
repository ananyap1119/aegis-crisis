import { Flame, PersonStanding, ShieldAlert, Wind, Crosshair, Users, AlertTriangle } from "lucide-react";
import type { AlertItem, AlertType, Severity } from "@/lib/types";

const ICONS: Record<AlertType, typeof Flame> = {
  FIRE: Flame,
  FALL: PersonStanding,
  INTRUSION: ShieldAlert,
  SMOKE: Wind,
  WEAPON: Crosshair,
  CROWD: Users,
};

const SEV_STYLES: Record<Severity, { badge: string; ring: string; text: string }> = {
  LOW: { badge: "bg-safe/15 text-safe border-safe/30", ring: "", text: "text-safe" },
  MEDIUM: { badge: "bg-monitor/15 text-monitor border-monitor/30", ring: "", text: "text-monitor" },
  HIGH: { badge: "bg-alert/15 text-alert border-alert/40", ring: "glow-alert", text: "text-alert" },
  CRITICAL: { badge: "bg-alert/25 text-alert border-alert/60", ring: "glow-alert animate-pulse-glow", text: "text-alert" },
};

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 5) return "just now";
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export function AlertsPanel({ alerts }: { alerts: AlertItem[] }) {
  return (
    <div className="flex h-full flex-col rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-foreground">Active Alerts</h2>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
            {alerts.length} signal{alerts.length === 1 ? "" : "s"} · live
          </p>
        </div>
        <AlertTriangle className={`h-4 w-4 ${alerts.length ? "text-alert" : "text-muted-foreground"}`} />
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {alerts.length === 0 ? (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center text-center">
            <div className="mb-3 h-10 w-10 rounded-full border border-safe/30 bg-safe/10 p-2.5">
              <ShieldAlert className="h-full w-full text-safe" />
            </div>
            <p className="text-sm font-medium text-foreground">All clear</p>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              No active threats detected
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {alerts.map((a) => {
              const Icon = ICONS[a.type];
              const sev = SEV_STYLES[a.severity];
              return (
                <li
                  key={a.id}
                  className={`group rounded-md border border-border bg-surface-elevated/60 p-3 transition-all duration-300 hover:bg-surface-elevated animate-fade-in-up ${sev.ring}`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md border ${sev.badge}`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-foreground">{a.type}</span>
                        <span
                          className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-semibold tracking-wider ${sev.badge}`}
                        >
                          {a.severity}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center justify-between gap-2 font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                        <span>{a.cameraId}</span>
                        <span>{timeAgo(a.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
