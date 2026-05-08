import type { TamperEvent } from "@/lib/types";

const TAMPER_COLOR: Record<string, string> = {
  blur:        "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
  shake:       "text-orange-400 bg-orange-400/10 border-orange-400/30",
  reposition:  "text-red-400   bg-red-400/10   border-red-400/30",
  hmac:        "text-purple-400 bg-purple-400/10 border-purple-400/30",
  clean:       "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
};

function TamperBadge({
  cameraId,
  tampered,
  hmacValid,
}: {
  cameraId: string;
  tampered: boolean;
  hmacValid: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded border border-border/40 bg-card/40 px-3 py-2">
      <span className="font-mono text-xs text-muted-foreground">{cameraId}</span>
      <div className="flex items-center gap-2">
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${
            tampered
              ? "border-red-500/40 bg-red-500/10 text-red-400"
              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
          }`}
        >
          {tampered ? "TAMPERED" : "CLEAN"}
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${
            hmacValid
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
              : "border-red-500/40 bg-red-500/10 text-red-400"
          }`}
        >
          HMAC {hmacValid ? "✓" : "✗"}
        </span>
      </div>
    </div>
  );
}

function TamperEventRow({ event }: { event: TamperEvent }) {
  const colorClass = TAMPER_COLOR[event.tamper_type] ?? TAMPER_COLOR.clean;
  const ts = new Date(event.timestamp * 1000).toLocaleTimeString();

  return (
    <div className="grid grid-cols-[auto_auto_1fr] items-center gap-x-3 rounded border border-border/30 bg-card/30 px-3 py-1.5 text-[11px]">
      <span className="font-mono text-muted-foreground/70">{ts}</span>
      <span
        className={`rounded border px-1.5 py-0.5 font-semibold uppercase tracking-wider ${colorClass}`}
      >
        {event.tamper_type}
      </span>
      <span className="truncate text-muted-foreground">{event.reason || event.camera_id}</span>
    </div>
  );
}

interface IntegrityPanelProps {
  tamperAlerts?: TamperEvent[];
  activeCameras?: string[];
}

export function IntegrityPanel({
  tamperAlerts = [],
  activeCameras = [],
}: IntegrityPanelProps) {
  // Build per-camera integrity status from the tamper alert list
  const cameraStatus: Record<
    string,
    { tampered: boolean; hmacValid: boolean }
  > = {};

  for (const cam of activeCameras) {
    cameraStatus[cam] = { tampered: false, hmacValid: true };
  }
  for (const evt of tamperAlerts) {
    if (!cameraStatus[evt.camera_id]) {
      cameraStatus[evt.camera_id] = { tampered: false, hmacValid: true };
    }
    cameraStatus[evt.camera_id].tampered = true;
    if (!evt.hmac_valid) {
      cameraStatus[evt.camera_id].hmacValid = false;
    }
  }

  const recentEvents = [...tamperAlerts]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 20);

  return (
    <div className="rounded-lg border border-border/50 bg-card/50 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-purple-400 shadow-[0_0_6px_theme(colors.purple.400)]" />
          <span className="font-mono text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">
            Frame Integrity
          </span>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground/60 uppercase tracking-widest">
          Aegis · HMAC
        </span>
      </div>

      <div className="space-y-4 p-4">
        {/* Per-camera tamper status badges */}
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60">
            Camera Status
          </p>
          {Object.keys(cameraStatus).length === 0 ? (
            <p className="text-center font-mono text-[11px] text-muted-foreground/50 py-2">
              No cameras registered
            </p>
          ) : (
            <div className="space-y-1.5">
              {Object.entries(cameraStatus).map(([cam, s]) => (
                <TamperBadge
                  key={cam}
                  cameraId={cam}
                  tampered={s.tampered}
                  hmacValid={s.hmacValid}
                />
              ))}
            </div>
          )}
        </div>

        {/* Recent tamper events */}
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60">
            Tamper Event Log
          </p>
          {recentEvents.length === 0 ? (
            <p className="text-center font-mono text-[11px] text-emerald-400/70 py-2">
              No tamper events — feed integrity nominal
            </p>
          ) : (
            <div className="max-h-48 space-y-1 overflow-y-auto pr-1">
              {recentEvents.map((evt) => (
                <TamperEventRow key={evt.id} event={evt} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
