import { useEffect, useRef, useState } from "react";
import type { StatusPayload } from "@/lib/types";
import { getMockStatus } from "@/lib/mock-status";

const ENDPOINT = "http://localhost:5000/api/status";
const POLL_MS = 400;

export function useStatus() {
  const [data, setData] = useState<StatusPayload>(() => getMockStatus());
  const [connected, setConnected] = useState(false);
  const failedRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 800);
        const res = await fetch(ENDPOINT, { signal: ctrl.signal });
        clearTimeout(t);
        if (!res.ok) throw new Error("bad status");
        const json = (await res.json()) as Partial<StatusPayload>;
        if (cancelled) return;
        failedRef.current = 0;
        setConnected(true);
        // Merge defensively — backend may not provide every field
        setData((prev: any) => ({
          frame: json.frame ?? prev.frame,
          status: json.status ?? prev.status,
          alerts: json.alerts ?? prev.alerts,
          logs: json.logs ?? prev.logs,
          metrics: { ...prev.metrics, ...(json.metrics ?? {}) },
          // Aegis-Crisis additions
          tamper_alerts: (json as any).tamper_alerts ?? prev.tamper_alerts ?? [],
          active_cameras: (json as any).active_cameras ?? prev.active_cameras ?? [],
          lifecycle_state: (json as any).lifecycle_state ?? prev.lifecycle_state,
          decision: (json as any).decision ?? prev.decision,
          severity: (json as any).severity ?? prev.severity,
          trust_score: (json as any).trust_score ?? prev.trust_score ?? 0,
          signals: (json as any).signals ?? prev.signals ?? [],
          llm_summary: (json as any).llm_summary ?? prev.llm_summary,
          incident_locked: (json as any).incident_locked ?? prev.incident_locked ?? false,
        }));
      } catch {
        failedRef.current++;
        if (failedRef.current > 2) {
          setConnected(false);
          // Fallback to mock so UI stays alive during dev
          setData(getMockStatus());
        }
      } finally {
        if (!cancelled) timer = setTimeout(tick, POLL_MS);
      }
    };

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return { data, connected };
}
