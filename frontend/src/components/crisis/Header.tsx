import { Activity } from "lucide-react";
import type { SystemStatus } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

export function Header({ status, connected }: { status: SystemStatus; connected: boolean }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border/60 bg-background/40 px-6 py-4 backdrop-blur-md">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-surface-elevated">
          <Activity className="h-4 w-4 text-primary" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-sm font-semibold tracking-tight text-foreground">
            AI Crisis Command Center
          </h1>
          <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            v2.4 · {connected ? "stream connected" : "simulation mode"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-2 font-mono text-[11px] text-muted-foreground sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-primary animate-blink" />
          <span>{new Date().toLocaleString()}</span>
        </div>
        <StatusBadge status={status} />
      </div>
    </header>
  );
}
