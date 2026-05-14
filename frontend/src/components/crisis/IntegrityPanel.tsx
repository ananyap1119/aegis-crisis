import type { TamperEvent } from "@/lib/types";

const TAMPER_COLOR: Record<string, string> = {
  blackout:   "text-red-400    bg-red-400/10    border-red-400/30",
  lens_spray: "text-orange-400 bg-orange-400/10 border-orange-400/30",
  feed_freeze:"text-purple-400 bg-purple-400/10 border-purple-400/30",
  reposition: "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
  glare:      "text-sky-400    bg-sky-400/10    border-sky-400/30",
  clean:      "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
};

const TAMPER_LABEL: Record<string, string> = {
  blackout:    "Blackout",
  lens_spray:  "Lens Spray",
  feed_freeze: "Feed Freeze",
  reposition:  "Reposition",
  glare:       "Glare",
  clean:       "Clean",
};

const TAMPER_CATEGORY: Record<string, string> = {
  blackout:    "physical",
  lens_spray:  "physical",
  feed_freeze: "digital",
  reposition:  "physical",
  glare:       "recovered",
  clean:       "—",
};

function TamperBadge({
  cameraId,
  tampered,
  glareRescued,
}: {
  cameraId: string;
  tampered: boolean;
  glareRescued?: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded border border-border/40 bg-card/40 px-3 py-2">
      <span className="font-mono text-xs text-muted-foreground">{cameraId}</span>
      <div className="flex items-center gap-2">
        {glareRescued && (
          <span className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border border-sky-500/40 bg-sky-500/10 text-sky-400">
            CLAHE ✓
          </span>
        )}
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${
            tampered
              ? "border-red-500/40 bg-red-500/10 text-red-400"
              : "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
          }`}
        >
          {tampered ? "TAMPERED" : "CLEAN"}
        </span>
      </div>
    </div>
  );
}

function TamperEventRow({ event }: { event: TamperEvent }) {
  const colorClass = TAMPER_COLOR[event.tamper_type] ?? TAMPER_COLOR.clean;
  const label      = TAMPER_LABEL[event.tamper_type] ?? event.tamper_type;
  const category   = TAMPER_CATEGORY[event.tamper_type] ?? "—";
  const ts = new Date(event.timestamp * 1000).toLocaleTimeString();

  return (
    <div className="grid grid-cols-[auto_auto_auto_1fr] items-center gap-x-2 rounded border border-border/30 bg-card/30 px-3 py-1.5 text-[11px]">
      <span className="font-mono text-muted-foreground/70">{ts}</span>
      <span className={`rounded border px-1.5 py-0.5 font-semibold uppercase tracking-wider ${colorClass}`}>
        {label}
      </span>
      <span className="font-mono text-[10px] text-muted-foreground/50 uppercase">{category}</span>
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
  const cameraStatus: Record<string, { tampered: boolean; glareRescued: boolean }> = {};

  for (const cam of activeCameras) {
    cameraStatus[cam] = { tampered: false, glareRescued: false };
  }
  for (const evt of tamperAlerts) {
    if (!cameraStatus[evt.camera_id]) {
      cameraStatus[evt.camera_id] = { tampered: false, glareRescued: false };
    }
    if (evt.tamper_type === "glare") {
      cameraStatus[evt.camera_id].glareRescued = true;
    } else {
      cameraStatus[evt.camera_id].tampered = true;
    }
  }

  const recentEvents = [...tamperAlerts]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 20);

  // Legend items for the check types
  const checks = [
    { label: "Brightness", sublabel: "blackout · lens spray", color: "bg-red-400" },
    { label: "SSIM Freeze", sublabel: "digital · feed loop", color: "bg-purple-400" },
    { label: "ORB Reposition", sublabel: "physical · moved cam", color: "bg-yellow-400" },
    { label: "CLAHE Glare", sublabel: "auto-recover · sky wash", color: "bg-sky-400" },
  ];

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
          Aegis · 3-Check
        </span>
      </div>

      <div className="space-y-4 p-4">

        {/* Aegis check legend */}
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground/60">
            Active Checks
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            {checks.map((c) => (
              <div key={c.label} className="flex items-center gap-2 rounded border border-border/30 bg-card/30 px-2.5 py-1.5">
                <div className={`h-1.5 w-1.5 rounded-full ${c.color} flex-shrink-0`} />
                <div>
                  <p className="font-mono text-[10px] font-semibold text-muted-foreground">{c.label}</p>
                  <p className="font-mono text-[9px] text-muted-foreground/50">{c.sublabel}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

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
                  glareRescued={s.glareRescued}
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
