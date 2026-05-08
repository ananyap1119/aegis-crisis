import type { SystemStatus } from "@/lib/types";

const MAP: Record<SystemStatus, { label: string; color: string; glow: string; dot: string }> = {
  SAFE: { label: "SAFE", color: "text-safe", glow: "glow-safe", dot: "bg-safe" },
  MONITOR: { label: "MONITOR", color: "text-monitor", glow: "glow-monitor", dot: "bg-monitor" },
  ALERT: { label: "ALERT", color: "text-alert", glow: "glow-alert", dot: "bg-alert" },
};

export function StatusBadge({ status }: { status: SystemStatus }) {
  const cfg = MAP[status];
  const isAlert = status === "ALERT";
  return (
    <div
      className={`flex items-center gap-2.5 rounded-md border bg-card/60 px-4 py-2 backdrop-blur transition-all duration-500 ${cfg.glow} ${isAlert ? "animate-pulse-glow" : ""}`}
    >
      <span className={`relative flex h-2.5 w-2.5`}>
        <span className={`absolute inline-flex h-full w-full rounded-full opacity-60 ${cfg.dot} ${isAlert ? "animate-ping" : ""}`} />
        <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${cfg.dot}`} />
      </span>
      <span className={`text-xs font-semibold tracking-[0.2em] ${cfg.color}`}>SYSTEM · {cfg.label}</span>
    </div>
  );
}
