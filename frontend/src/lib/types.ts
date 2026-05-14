export type SystemStatus = "SAFE" | "MONITOR" | "ALERT";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertType = "FIRE" | "FALL" | "INTRUSION" | "SMOKE" | "WEAPON" | "CROWD";

export interface AlertItem {
  id: string;
  type: AlertType;
  severity: Severity;
  cameraId: string;
  timestamp: string;
  message?: string;
}

export interface LogItem {
  id: string;
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR" | "AGENT";
  message: string;
}

export interface Metrics {
  confidence: number; // 0-100
  fps: number;
  latencyMs: number;
  modelsActive: number;
  uptime: string;
}

export type TamperType = "blackout" | "lens_spray" | "feed_freeze" | "reposition" | "clean" | "glare";

export interface TamperEvent {
  id: number;
  session_id: string;
  camera_id: string;
  timestamp: number;
  tamper_type: TamperType;
  reason: string;
  hmac_valid: boolean;
}

export interface CameraIntegrityStatus {
  camera_id: string;
  tampered: boolean;
  tamper_type?: TamperType;
  hmac_valid: boolean;
  glare_rescued?: boolean;
  last_checked: string;
}

export interface StatusPayload {
  frame: string | null; // base64 (no prefix or with prefix)
  status: SystemStatus;
  alerts: AlertItem[];
  logs: LogItem[];
  metrics: Metrics;
  // Aegis-Crisis additions
  tamper_alerts?: TamperEvent[];
  active_cameras?: string[];
  lifecycle_state?: string;
  decision?: string | null;
  severity?: string | null;
  trust_score?: number;
  signals?: { source: string; text: string; confidence: number }[];
  llm_summary?: string | null;
  incident_locked?: boolean;
}
