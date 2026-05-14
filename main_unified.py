"""
SecureEye — Unified Entry Point

Pipeline per frame:
  [Camera Feed]
       ↓
  [tamper_agent.check_frame]  — brightness, SSIM freeze, ORB reposition
       ↓ tampered → log to tamper_events, skip crisis pipeline
       ↓ clean    → CLAHE-rescued frame
  [vision_agent.process_frame]
       ↓
  [TemporalEventTracker.stabilize]
       ↓
  [LangGraph: risk → decision → action]
       ↓
  [db.log_crisis_event + unified_server.emit_crisis_update]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

# Ensure backend/ is on sys.path so all flat imports inside backend/ work.
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import cv2
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

import db
import unified_server as api_server
from alert_system import send_alert
from decision_engine import decision_engine, detect_danger
from pipeline_support import (
    DEFAULT_CAMERA_ID,
    CrisisState,
    TemporalEventTracker,
    configure_logging,
    get_env_bool,
    normalize_video_source,
)
import tamper_agent
from vision_agent import process_frame

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_SOURCE = os.getenv("CRISIS_VIDEO_SOURCE", "0")
DEFAULT_LOG_LEVEL    = os.getenv("CRISIS_LOG_LEVEL", "INFO")
DEFAULT_LOCATION     = os.getenv("CRISIS_LOCATION", "demo-site")
DEFAULT_DEMO_MODE    = get_env_bool("DEMO_MODE", False)
MAX_HISTORY_ITEMS    = 25

history_by_camera: dict[str, list[dict[str, Any]]] = defaultdict(list)


def normalize_choice(value: Any, allowed: set[str], fallback: str) -> str:
    candidate = str(value).upper()
    return candidate if candidate in allowed else fallback


def build_initial_state(vision_event: dict) -> CrisisState:
    return {
        "camera_id": vision_event["camera_id"],
        "frame_index": vision_event["frame_index"],
        "vision_event": vision_event,
        "crisis": detect_danger(vision_event),
    }


# ── LangGraph agent nodes ─────────────────────────────────────────────────────

def _build_risk_score(state: CrisisState) -> dict:
    """
    Deterministic risk scoring — no LLM required.

    Inputs:
      - crisis type from detect_danger (FIRE / MEDICAL / BOTH / SAFE)
      - Gate 1 fire score + tier from vision_event
      - Gate 1 fall state from vision_event
      - historical repetition count for this camera
    """
    vision_event = state["vision_event"]
    crisis       = state["crisis"]
    history      = state.get("history", [])
    repeated     = sum(1 for h in history if h.get("crisis") == crisis)

    fire_score = float(vision_event.get("fire_gate1_score", 0.0))
    fire_tier  = vision_event.get("fire_tier", "SAFE")
    fall_state = vision_event.get("fall_gate1_state", "IDLE")

    tier_boost = {"TIER_3": 0.30, "TIER_2": 0.15, "TIER_1": 0.05, "SAFE": 0.0}
    fall_map   = {"ESCALATE": 0.85, "WATCHING": 0.50, "IDLE": 0.25, "SUPPRESSED": 0.05}

    if crisis == "BOTH":
        base = 0.90
    elif crisis == "FIRE":
        base = fire_score + tier_boost.get(fire_tier, 0.0)
    elif crisis == "MEDICAL":
        base = fall_map.get(fall_state, 0.25)
    else:
        base = 0.0

    if repeated >= 2:
        base = min(base + 0.10, 1.0)

    base = float(min(max(base, 0.0), 1.0))

    if base >= 0.85 or crisis == "BOTH":
        severity = "CRITICAL"
    elif base >= 0.65:
        severity = "HIGH"
    elif base >= 0.40:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    urgency = "IMMEDIATE" if severity in {"HIGH", "CRITICAL"} else "MONITOR"
    return {
        "severity": severity,
        "urgency":  urgency,
        "note": f"score={base:.2f} tier={fire_tier} fall={fall_state} repeat={repeated}",
    }


def _build_decision_output(state: CrisisState) -> dict:
    danger   = state["crisis"]
    action   = decision_engine(danger)
    severity = state["risk_output"]["severity"]
    priority = "HIGH" if severity in {"HIGH", "CRITICAL"} else "MEDIUM"
    if action == "NO_ACTION":
        priority = "LOW"
    return {"danger": danger, "action": action, "priority": priority}


def _build_action_output(state: CrisisState) -> dict:
    action = state["decision_output"]["action"]
    danger = state["decision_output"]["danger"]
    tool   = "send_alert" if action != "NO_ACTION" else "log_event"
    if action == "NO_ACTION":
        message = f"No escalation for {state['camera_id']} frame {state['frame_index']}."
    else:
        message = (f"{danger} on {state['camera_id']} frame {state['frame_index']}; "
                   f"dispatching {action.lower()}.")
    return {"action": action, "tool": tool, "message": message}


def risk_agent(state: CrisisState) -> CrisisState:
    history = history_by_camera[state["camera_id"]]
    state["history"] = list(history)
    state["risk_output"] = _build_risk_score(state)
    history.append({"frame_index": state["frame_index"], "crisis": state["crisis"],
                    "severity": state["risk_output"]["severity"]})
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]
    return state


def decision_agent(state: CrisisState) -> CrisisState:
    state["decision_output"] = _build_decision_output(state)
    return state


def action_agent(state: CrisisState) -> CrisisState:
    state["action_output"] = _build_action_output(state)
    return state


def build_graph():
    graph = StateGraph(CrisisState)
    graph.add_node("risk_node",     risk_agent)
    graph.add_node("decision_node", decision_agent)
    graph.add_node("action_node",   action_agent)
    graph.set_entry_point("risk_node")
    graph.add_edge("risk_node",     "decision_node")
    graph.add_edge("decision_node", "action_node")
    graph.add_edge("action_node",   END)
    return graph.compile()


# ── Core pipeline loop ────────────────────────────────────────────────────────

CAMERA_LOCATIONS = {
    "fall":   "Mall - Floor 2 - Gym Area",
    "fire":   "Industrial Site - Sector B - Warehouse",
    "webcam": "Remote Office - Entrance",
}


def run_live_graph(
    video_source: str,
    camera_id: str = DEFAULT_CAMERA_ID,
    session_id: str | None = None,
    display: bool = False,
    max_frames: int | None = None,
    skip_hmac: bool = True,
    stop_event: threading.Event | None = None,
) -> None:
    """
    Main per-camera pipeline loop.

    For each frame:
      1. tamper_agent.check_frame — if tampered, log & skip
      2. vision_agent.process_frame on CLAHE-rescued frame
      3. TemporalEventTracker.stabilize
      4. LangGraph pipeline
      5. DB logging + SocketIO emission
    """
    if session_id is None:
        session_id = str(uuid.uuid4())

    graph_app = build_graph()
    tracker = TemporalEventTracker()
    _src = normalize_video_source(video_source)
    if isinstance(_src, int):
        # Use DirectShow on Windows to avoid MSMF errors with webcam
        cap = cv2.VideoCapture(_src, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(_src)  # fallback
    else:
        cap = cv2.VideoCapture(_src)
    if not cap.isOpened():
        print(f"[System] Could not open video source: {video_source}")
        api_server.update_crisis_state({"logs": api_server.get_crisis_state()["logs"] + [
            f"[Error] Could not open camera/video: {video_source}"
        ]})
        return

    FRAME_SKIP = 2
    video_filename = os.path.basename(str(video_source))
    location = CAMERA_LOCATIONS.get(camera_id.lower(), f"Site: {video_filename}")
    event_type = ("fire" if "fire" in video_filename.lower()
                  else ("fall" if "fall" in video_filename.lower() else None))

    incident_locked = False

    api_server.update_crisis_state({
        "decision": None, "severity": None, "trust_score": 0.0,
        "location": location, "current_video": video_filename,
        "lifecycle_state": "MONITORING",
        "confidence_explanation": [], "decision_reason": None,
        "signals": [], "llm_summary": None, "incident_locked": False,
        "status": "SAFE",
        "logs": [f"[System] Starting video: {video_filename}"]
    })

    frame_index = 0
    try:
        while True:
            if stop_event and stop_event.is_set():
                break
            if max_frames is not None and frame_index >= max_frames:
                break
            ret, frame = cap.read()
            if not ret:
                break

            # ── Step 1: Tamper detection ──────────────────────────────────────
            t_result = tamper_agent.check_frame(frame, camera_id,
                                                check_hmac=not skip_hmac)

            if t_result["tampered"]:
                ts = time.time()
                db.log_tamper_event(
                    session_id=session_id,
                    camera_id=camera_id,
                    timestamp=ts,
                    tamper_type=t_result["tamper_type"],
                    reason=t_result["reason"],
                    hmac_valid=t_result["hmac_valid"],
                )
                tamper_payload = {
                    "camera_id": camera_id,
                    "session_id": session_id,
                    "timestamp": ts,
                    "tamper_type": t_result["tamper_type"],
                    "reason": t_result["reason"],
                    "hmac_valid": t_result["hmac_valid"],
                }
                api_server.emit_tamper_update(tamper_payload)
                state = api_server.get_crisis_state()
                api_server.update_crisis_state({
                    "logs": state["logs"] + [
                        f"[Tamper] {t_result['tamper_type'].upper()} on {camera_id}: {t_result['reason']}"
                    ]
                })
                frame_index += 1
                continue  # Skip crisis pipeline for tampered frame

            # Use CLAHE-rescued frame for crisis inference
            clean_frame = t_result["preprocessed_frame"]

            # ── Step 2: Vision inference ──────────────────────────────────────
            live_event = process_frame(clean_frame, camera_id=camera_id, frame_index=frame_index)
            # Annotate tamper fields
            live_event["tamper_status"] = False
            live_event["tamper_reason"] = ""

            stable_event = tracker.stabilize(live_event, clean_frame)
            danger = detect_danger(stable_event)
            attention_state = danger if danger != "SAFE" else stable_event.get("validation_state", "SAFE")

            if api_server.get_crisis_state()["incident_locked"] and not incident_locked:
                incident_locked = True

            # ── LangGraph pipeline ────────────────────────────────────────────
            if not incident_locked and attention_state != "SAFE":
                result = graph_app.invoke(build_initial_state(stable_event))
                action   = result["action_output"]["action"]
                severity = result["risk_output"]["severity"]
                trust    = stable_event.get("confidence", 0.0)

                # Always log to DB for correlated analysis
                db.log_crisis_event(
                    session_id=session_id,
                    camera_id=camera_id,
                    timestamp=time.time(),
                    frame_index=frame_index,
                    fire=stable_event.get("fire", False),
                    smoke=stable_event.get("smoke", False),
                    person=stable_event.get("person", False),
                    fall=stable_event.get("fall_detected", False),
                    confidence=trust,
                    decision=action,
                    severity=severity,
                )

                crisis_payload = {
                    "camera_id": camera_id,
                    "session_id": session_id,
                    "frame_index": frame_index,
                    "fire": stable_event.get("fire", False),
                    "smoke": stable_event.get("smoke", False),
                    "person": stable_event.get("person", False),
                    "fall": stable_event.get("fall_detected", False),
                    "confidence": trust,
                    "decision": action,
                    "severity": severity,
                    "tamper_verified": True,
                }
                api_server.emit_crisis_update(crisis_payload)

                if action != "NO_ACTION" and trust > 0.4:
                    is_fire = "FIRE" in action
                    note    = result["risk_output"]["note"]
                    explanation = [
                        f"{'Fire/Smoke' if is_fire else 'Fall'} signature detected",
                        "Temporal consistency verified (3+ frames)",
                        f"Risk assessment: {note}",
                    ]
                    incident_locked = True
                    send_alert(action, camera_id=camera_id,
                               details=result["action_output"]["message"])
                    state = api_server.get_crisis_state()
                    alert_item = {
                        "id": f"{camera_id}-{frame_index}",
                        "type": "FIRE" if is_fire else "FALL",
                        "severity": severity,
                        "cameraId": camera_id.upper(),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    existing_alerts = state.get("alerts", [])
                    api_server.update_crisis_state({
                        "decision": action,
                        "severity": severity,
                        "trust_score": round(trust, 2),
                        "lifecycle_state": "DISPATCHED",
                        "confidence_explanation": explanation,
                        "decision_reason": note,
                        "status": "ALERT",
                        "incident_locked": True,
                        "alerts": [alert_item] + existing_alerts,
                        "logs": state["logs"] + [f"[Decision] {action} — {note}"],
                    })

            # ── Dashboard frame update ────────────────────────────────────────
            if frame_index % FRAME_SKIP == 0:
                api_server.update_crisis_state(
                    {"frame": api_server.encode_frame(clean_frame)}
                )

            frame_index += 1

        state = api_server.get_crisis_state()
        api_server.update_crisis_state({
            "logs": state["logs"] + [f"[System] Completed video: {video_filename}"]
        })
    finally:
        cap.release()
        cv2.destroyAllWindows()


# ── Pipeline Controller ───────────────────────────────────────────────────────

class PipelineController:
    """Manages the active pipeline thread. Used by demo API endpoints."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def play(self, source: str, session_id: str | None = None) -> None:
        self.stop()
        self._stop_event.clear()
        filename = os.path.basename(str(source))
        camera_id = (
            "fall"  if "fall"  in filename.lower() else
            "fire"  if "fire"  in filename.lower() else
            "webcam"
        )
        sid = session_id or str(uuid.uuid4())
        print(f"[Pipeline] Starting: {source} (camera={camera_id} session={sid})")
        self._thread = threading.Thread(
            target=run_live_graph,
            kwargs=dict(
                video_source=source,
                camera_id=camera_id,
                session_id=sid,
                skip_hmac=True,
                stop_event=self._stop_event,
            ),
            daemon=True,
        )
        self._thread.start()

    def play_all(self, session_id: str | None = None) -> None:
        """Play fall1 → fire1 → fire2 in sequence."""
        self.stop()
        self._stop_event.clear()
        sources = [
            ("videos/fall1.mp4", "fall"),
            ("videos/fire1.mp4", "fire"),
            ("videos/fire2.mp4", "fire"),
        ]
        sid = session_id or str(uuid.uuid4())

        def _run_sequence():
            for source, camera_id in sources:
                if self._stop_event.is_set():
                    break
                print(f"[Pipeline] Sequence: {source} (camera={camera_id})")
                run_live_graph(
                    video_source=source,
                    camera_id=camera_id,
                    session_id=sid,
                    skip_hmac=True,
                    stop_event=self._stop_event,
                )

        self._thread = threading.Thread(target=_run_sequence, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SecureEye unified pipeline")
    parser.add_argument("--video", default=None,
                        help="Video file or camera index to start automatically")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    db.init_db()

    controller = PipelineController()
    api_server.start_server()
    api_server.set_pipeline_controller(controller)

    # Auto-start a source if passed on CLI; otherwise wait for demo panel
    if args.video:
        controller.play(args.video)
    else:
        print("[SecureEye] Ready. Open http://localhost:8080 and use the Demo Panel to start.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        controller.stop()
        print("\n[SecureEye] Shutdown.")


if __name__ == "__main__":
    main()
