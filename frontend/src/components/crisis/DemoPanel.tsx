import { useState } from "react";

const API = "http://localhost:5000";

async function post(path: string, body: object) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
}

type BtnState = "idle" | "loading" | "ok" | "err";

function ActionButton({
  label,
  sublabel,
  color,
  onClick,
}: {
  label: string;
  sublabel?: string;
  color: "blue" | "red" | "orange" | "purple" | "green" | "gray";
  onClick: () => Promise<void>;
}) {
  const [state, setState] = useState<BtnState>("idle");

  const colorMap = {
    blue:   "border-blue-500/40   bg-blue-500/10   text-blue-300   hover:bg-blue-500/20",
    red:    "border-red-500/40    bg-red-500/10    text-red-300    hover:bg-red-500/20",
    orange: "border-orange-500/40 bg-orange-500/10 text-orange-300 hover:bg-orange-500/20",
    purple: "border-purple-500/40 bg-purple-500/10 text-purple-300 hover:bg-purple-500/20",
    green:  "border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20",
    gray:   "border-border/40     bg-card/40       text-muted-foreground hover:bg-card/60",
  };

  const handle = async () => {
    setState("loading");
    try {
      await onClick();
      setState("ok");
      setTimeout(() => setState("idle"), 1500);
    } catch {
      setState("err");
      setTimeout(() => setState("idle"), 2000);
    }
  };

  const icon = state === "loading" ? "…" : state === "ok" ? "✓" : state === "err" ? "✗" : null;

  return (
    <button
      onClick={handle}
      disabled={state === "loading"}
      className={`flex flex-col items-start rounded border px-3 py-2.5 text-left transition-colors disabled:opacity-60 ${colorMap[color]}`}
    >
      <span className="flex w-full items-center justify-between gap-2 font-mono text-[11px] font-semibold uppercase tracking-wide">
        {label}
        {icon && <span className="text-[10px]">{icon}</span>}
      </span>
      {sublabel && (
        <span className="mt-0.5 font-mono text-[9px] opacity-60 leading-tight">{sublabel}</span>
      )}
    </button>
  );
}

const VIDEO_OPTIONS = [
  { label: "Fall Detection  —  fall1.mp4",   source: "videos/fall1.mp4" },
  { label: "Fire Detection 1  —  fire1.mp4", source: "videos/fire1.mp4" },
  { label: "Fire Detection 2  —  fire2.mp4", source: "videos/fire2.mp4" },
  { label: "Live Webcam  —  camera 0",       source: "0"                },
];

export function DemoPanel() {
  const [selected, setSelected] = useState(VIDEO_OPTIONS[0].source);
  const [playState, setPlayState] = useState<BtnState>("idle");

  const handlePlay = async () => {
    setPlayState("loading");
    try {
      await post("/api/demo/play", { source: selected });
      setPlayState("ok");
      setTimeout(() => setPlayState("idle"), 1500);
    } catch {
      setPlayState("err");
      setTimeout(() => setPlayState("idle"), 2000);
    }
  };

  const injectTamper = (type: string) =>
    post("/api/demo/inject_tamper", { type, camera_id: "demo-cam" });

  const stopPipeline  = () => post("/api/demo/stop", {});
  const resetDashboard = () => fetch(`${API}/api/reset`, { method: "POST" }).then(() => {});

  const playIcon = playState === "loading" ? "…" : playState === "ok" ? "✓" : playState === "err" ? "✗" : "▶";

  return (
    <div className="rounded-lg border border-border/50 bg-card/50 backdrop-blur-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-yellow-400 shadow-[0_0_6px_theme(colors.yellow.400)]" />
          <span className="font-mono text-xs font-semibold uppercase tracking-[0.15em] text-muted-foreground">
            Demo Controls
          </span>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground/60 uppercase tracking-widest">
          SecureEye · Live Demo
        </span>
      </div>

      <div className="p-4 space-y-5">

        {/* ── Video Source Selector ── */}
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground/60">
            Video Source
          </p>
          <div className="flex gap-2">
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="flex-1 rounded border border-border/50 bg-card/60 px-3 py-2 font-mono text-[11px] text-muted-foreground focus:border-blue-500/60 focus:outline-none"
            >
              {VIDEO_OPTIONS.map((o) => (
                <option key={o.source} value={o.source}>
                  {o.label}
                </option>
              ))}
            </select>
            <button
              onClick={handlePlay}
              disabled={playState === "loading"}
              className="flex items-center gap-1.5 rounded border border-blue-500/40 bg-blue-500/10 px-4 py-2 font-mono text-[11px] font-semibold uppercase tracking-wide text-blue-300 transition-colors hover:bg-blue-500/20 disabled:opacity-60"
            >
              <span>{playIcon}</span>
              <span>Play</span>
            </button>
          </div>
        </div>

        {/* ── Tamper Injection ── */}
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground/60">
            Tamper Detection (Aegis)
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
            <ActionButton label="🌑 Blackout"    sublabel="physical → guard"  color="gray"   onClick={() => injectTamper("blackout")} />
            <ActionButton label="💨 Lens Spray"  sublabel="physical · CLAHE"  color="gray"   onClick={() => injectTamper("lens_spray")} />
            <ActionButton label="🔄 Reposition"  sublabel="physical · ORB"    color="gray"   onClick={() => injectTamper("reposition")} />
            <ActionButton label="❄️ Feed Freeze" sublabel="digital → IT team" color="purple" onClick={() => injectTamper("feed_freeze")} />
            <ActionButton label="⚡ Coordinated" sublabel="both · CRITICAL"   color="red"    onClick={() => injectTamper("coordinated")} />
          </div>
        </div>

        {/* ── Controls ── */}
        <div>
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground/60">
            Controls
          </p>
          <div className="flex gap-2">
            <ActionButton label="⏹ Stop"           sublabel="halt pipeline"     color="gray" onClick={stopPipeline} />
            <ActionButton label="↺ Reset Dashboard" sublabel="clear alerts + logs" color="gray" onClick={resetDashboard} />
          </div>
        </div>

      </div>
    </div>
  );
}
