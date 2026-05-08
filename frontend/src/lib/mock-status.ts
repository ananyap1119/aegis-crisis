import type { StatusPayload, AlertItem, LogItem, SystemStatus, AlertType, Severity } from "./types";

const ALERT_TYPES: AlertType[] = ["FIRE", "FALL", "INTRUSION", "SMOKE", "WEAPON", "CROWD"];
const SEVERITIES: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const CAMERAS = ["CAM-01", "CAM-02", "CAM-03", "CAM-04", "CAM-07", "CAM-12"];

const AGENT_MESSAGES = [
  "Analyzing motion vectors across CAM-02…",
  "Vision model: object detection pass complete",
  "Confidence delta: +2.4% (normal range)",
  "Cross-referencing thermal signature with baseline",
  "Heuristic check: no anomaly detected",
  "Reasoning: scene state stable",
  "Tracking 4 entities across viewport",
  "Frame buffer flushed — 30 FPS sustained",
  "Agent: monitoring perimeter sensors",
  "LLM context window updated",
  "No correlated alerts in last 30s window",
  "Audio classifier: ambient profile nominal",
];

let alertCounter = 0;
let logCounter = 0;

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function nowIso() {
  return new Date().toISOString();
}

let logs: LogItem[] = [];
let alerts: AlertItem[] = [];
let tick = 0;

export function getMockStatus(): StatusPayload {
  tick++;

  // Add a new log every ~3 ticks
  if (tick % 3 === 0) {
    logs = [
      {
        id: `log-${logCounter++}`,
        timestamp: nowIso(),
        level: pick(["INFO", "INFO", "INFO", "AGENT", "AGENT", "WARN"] as const),
        message: pick(AGENT_MESSAGES),
      },
      ...logs,
    ].slice(0, 80);
  }

  // Occasionally spawn an alert
  if (Math.random() < 0.04 && alerts.length < 8) {
    alerts = [
      {
        id: `alert-${alertCounter++}`,
        type: pick(ALERT_TYPES),
        severity: pick(SEVERITIES),
        cameraId: pick(CAMERAS),
        timestamp: nowIso(),
      },
      ...alerts,
    ].slice(0, 12);
  }

  // Occasionally clear oldest
  if (Math.random() < 0.02 && alerts.length > 0) {
    alerts = alerts.slice(0, -1);
  }

  const hasCritical = alerts.some((a) => a.severity === "CRITICAL" || a.severity === "HIGH");
  const status: SystemStatus = hasCritical ? "ALERT" : alerts.length > 0 ? "MONITOR" : "SAFE";

  const baseConfidence = status === "SAFE" ? 95 : status === "MONITOR" ? 82 : 68;
  const confidence = Math.max(40, Math.min(99, baseConfidence + (Math.random() * 6 - 3)));

  return {
    frame: null,
    status,
    alerts,
    logs,
    metrics: {
      confidence,
      fps: 28 + Math.random() * 4,
      latencyMs: 40 + Math.random() * 20,
      modelsActive: 4,
      uptime: "12d 04:22:18",
    },
  };
}
