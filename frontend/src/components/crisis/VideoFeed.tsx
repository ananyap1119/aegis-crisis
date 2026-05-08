import type { SystemStatus } from "@/lib/types";

interface Props {
  frame: string | null;
  status: SystemStatus;
  cameraLabel?: string;
}

export function VideoFeed({ frame, status, cameraLabel = "CAM-02 · MAIN ENTRANCE" }: Props) {
  const src = frame
    ? frame.startsWith("data:")
      ? frame
      : `data:image/jpeg;base64,${frame}`
    : null;

  const glow =
    status === "ALERT" ? "glow-alert" : status === "MONITOR" ? "glow-monitor" : "glow-safe";

  return (
    <div
      className={`group relative overflow-hidden rounded-lg border border-border bg-card transition-all duration-500 ${glow}`}
    >
      <div className="relative aspect-video w-full bg-black">
        {src ? (
          <img src={src} alt="Live video feed" className="h-full w-full object-contain" />
        ) : (
          <div className="grid-bg absolute inset-0 flex items-center justify-center">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary to-transparent animate-scan" />
            <div className="text-center">
              <div className="mx-auto mb-3 h-2 w-2 animate-blink rounded-full bg-primary" />
              <p className="font-mono text-xs uppercase tracking-[0.3em] text-muted-foreground">
                Awaiting frame stream
              </p>
              <p className="mt-1 font-mono text-[10px] text-muted-foreground/60">
                localhost:8000/status
              </p>
            </div>
          </div>
        )}

        {/* Top gradient overlay for readability */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-black/70 to-transparent" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/70 to-transparent" />

        {/* Camera label */}
        <div className="absolute left-4 top-4 flex items-center gap-2 rounded-md border border-white/10 bg-black/50 px-2.5 py-1.5 backdrop-blur">
          <span className="h-1.5 w-1.5 animate-blink rounded-full bg-alert" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-white">
            {cameraLabel}
          </span>
        </div>

        {/* Status indicator top-right */}
        <div className="absolute right-4 top-4 flex items-center gap-2 rounded-md border border-white/10 bg-black/50 px-2.5 py-1.5 backdrop-blur">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/80">REC</span>
          <span className="h-2 w-2 rounded-full bg-alert animate-pulse-alert" />
        </div>

        {/* Bottom HUD */}
        <div className="absolute inset-x-4 bottom-4 flex items-end justify-between font-mono text-[10px] uppercase tracking-[0.2em] text-white/70">
          <div>
            <div>RES · 1920×1080</div>
            <div className="text-white/50">CODEC · H.264</div>
          </div>
          <div className="text-right">
            <div>{new Date().toLocaleTimeString()}</div>
            <div className="text-white/50">SYNC · OK</div>
          </div>
        </div>
      </div>
    </div>
  );
}
