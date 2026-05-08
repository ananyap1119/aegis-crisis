import { useEffect, useRef } from "react";
import type { LogItem } from "@/lib/types";

const LEVEL_COLORS: Record<LogItem["level"], string> = {
  INFO: "text-primary",
  AGENT: "text-safe",
  WARN: "text-monitor",
  ERROR: "text-alert",
};

export function AgentTimeline({ logs }: { logs: LogItem[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const prevTopId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (logs[0]?.id !== prevTopId.current) {
      ref.current?.scrollTo({ top: 0, behavior: "smooth" });
      prevTopId.current = logs[0]?.id;
    }
  }, [logs]);

  return (
    <div className="rounded-lg border border-border bg-card/70 backdrop-blur">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex gap-1.5">
            <span className="h-2 w-2 rounded-full bg-alert/70" />
            <span className="h-2 w-2 rounded-full bg-monitor/70" />
            <span className="h-2 w-2 rounded-full bg-safe/70" />
          </div>
          <h2 className="text-sm font-semibold tracking-tight text-foreground">
            Agent Intelligence Timeline
          </h2>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          stdout · {logs.length} events
        </span>
      </div>

      <div
        ref={ref}
        className="max-h-72 overflow-y-auto px-5 py-3 font-mono text-xs leading-relaxed"
      >
        {logs.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground">
            <span className="animate-blink">▍</span> awaiting agent output…
          </div>
        ) : (
          <ul className="space-y-1.5">
            {logs.map((log, i) => (
              <li
                key={log.id}
                className="flex items-start gap-3 animate-fade-in-up"
                style={{ animationDelay: i === 0 ? "0ms" : undefined }}
              >
                <span className="shrink-0 text-muted-foreground/60">
                  {new Date(log.timestamp).toLocaleTimeString("en-GB", { hour12: false })}
                </span>
                <span className={`shrink-0 font-semibold ${LEVEL_COLORS[log.level]}`}>
                  [{log.level}]
                </span>
                <span className="text-foreground/90">{log.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
