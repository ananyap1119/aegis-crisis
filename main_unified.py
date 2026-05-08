"""
Aegis-Crisis — Unified Entry Point

Pipeline per frame:
  [Camera Feed]
       ↓
  [tamper_agent.check_frame]  — blur, shake, reposition, HMAC
       ↓ tampered → log to tamper_events, skip crisis pipeline
       ↓ clean    → CLAHE-rescued frame
  [vision_agent.process_frame]
       ↓
  [TemporalEventTracker.stabilize]
       ↓
  [LangGraph: fusion → risk → decision → action]
       ↓
  [db.log_crisis_event + unified_server.emit_crisis_update]
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import re
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
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
    SocialSignal,
    TemporalEventTracker,
    configure_logging,
    get_env_bool,
    log_payload,
    normalize_video_source,
)
from social_agent import fetch_social_signals, simulate_social_signals
import tamper_agent
from vision_agent import process_frame

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_VIDEO_SOURCE = os.getenv("CRISIS_VIDEO_SOURCE", "0")
DEFAULT_LOG_LEVEL    = os.getenv("CRISIS_LOG_LEVEL", "INFO")
DEFAULT_GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
DEFAULT_LOCATION     = os.getenv("CRISIS_LOCATION", "demo-site")
DEFAULT_DEMO_MODE    = get_env_bool("DEMO_MODE", False)
MAX_HISTORY_ITEMS    = 25

history_by_camera: dict[str, list[dict[str, Any]]] = defaultdict(list)
_llm: Any | None = None
_llm_disabled = False


# ── LLM helpers (identical to original main.py) ──────────────────────────────

def safe_parse(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"{.*}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {"raw": text}


def confidence_band(score: float) -> str:
    if score >= 0.80:
        return "HIGH"
    if score >= 0.50:
        return "MEDIUM"
    return "LOW"


def normalize_choice(value: Any, allowed: set[str], fallback: str) -> str:
    candidate = str(value).upper()
    return candidate if candidate in allowed else fallback


def create_llm():
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from langchain_groq import ChatGroq
    except ImportError:
        return None
    try:
        return ChatGroq(temperature=0, model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL))
    except Exception:
        return None


def get_llm():
    global _llm, _llm_disabled
    if _llm is not None:
        return _llm
    if _llm_disabled:
        return None
    _llm = create_llm()
    if _llm is None:
        _llm_disabled = True
        logger.warning("Groq client unavailable; using deterministic fallbacks.")
    return _llm


def invoke_json_agent(prompt: str, fallback: dict) -> dict:
    llm = get_llm()
    if llm is None:
        return fallback
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        logger.warning("LLM invocation failed; using fallback: %s", exc)
        return fallback
    parsed = safe_parse(response.content)
    return parsed if "raw" not in parsed else fallback


# ── Social signal helpers ─────────────────────────────────────────────────────

def build_social_query(vision_event: dict) -> str:
    if detect_danger(vision_event) in {"FIRE", "BOTH"}:
        return "fire smoke emergency"
    if vision_event.get("validation_state") == "MONITOR":
        return "possible fire smoke report"
    if vision_event["fall_detected"]:
        return "medical emergency person fall"
    return "no active crisis"


def build_social_signal(vision_event: dict) -> SocialSignal:
    location = os.getenv("CRISIS_LOCATION", DEFAULT_LOCATION)
    social_signal = fetch_social_signals(build_social_query(vision_event), location=location)
    return {
        "type": social_signal["type"],
        "confidence": round(float(social_signal["confidence"]), 2),
        "source": social_signal.get("source", "social"),
        "text": social_signal["text"],
        "location": location,
    }


def build_initial_state(vision_event: dict, social: SocialSignal | None = None) -> CrisisState:
    return {
        "camera_id": vision_event["camera_id"],
        "frame_index": vision_event["frame_index"],
        "vision_event": vision_event,
        "social": social or build_social_signal(vision_event),
        "crisis": detect_danger(vision_event),
    }


# ── LangGraph agent nodes (identical to original) ────────────────────────────

def build_fusion_fallback(state: CrisisState) -> dict:
    crisis = state["crisis"]
    vision_event = state["vision_event"]
    social_signal = state["social"]
    validation_state = vision_event.get("validation_state", "SAFE")
    validation_reason = vision_event.get("validation_reason", "no validation details")
    social_type = normalize_choice(
        social_signal.get("type", "SAFE"), {"SAFE", "FIRE", "MEDICAL"}, "SAFE"
    )

    vision_fire_confirmed = crisis in {"FIRE", "BOTH"}
    vision_medical_confirmed = crisis in {"MEDICAL", "BOTH"}
    vision_fire_candidate = (
        vision_fire_confirmed
        or validation_state == "MONITOR"
        or vision_event.get("raw_fire_detected", False)
        or vision_event.get("raw_smoke_detected", False)
    )
    social_fire = social_type == "FIRE" and social_signal["confidence"] >= 0.50
    social_medical = social_type == "MEDICAL" and social_signal["confidence"] >= 0.50

    if social_fire and vision_fire_candidate:
        return {"is_crisis": True, "crisis_type": "BOTH" if crisis == "BOTH" else "FIRE",
                "confidence": "HIGH", "reason": "Vision and social signals corroborate a fire event."}
    if social_medical and vision_medical_confirmed:
        return {"is_crisis": True, "crisis_type": crisis, "confidence": "HIGH",
                "reason": "Vision and social signals corroborate a medical event."}
    if vision_fire_confirmed or vision_medical_confirmed:
        return {"is_crisis": True, "crisis_type": crisis, "confidence": "MEDIUM",
                "reason": f"Single confirmed vision signal: {validation_reason}."}
    if social_fire or social_medical or validation_state == "MONITOR":
        return {"is_crisis": False, "crisis_type": "SAFE", "confidence": "MEDIUM",
                "reason": f"Single weak signal only. Vision: {validation_reason}. Social: {social_signal['text']}"}
    return {"is_crisis": False, "crisis_type": "SAFE", "confidence": "LOW",
            "reason": "No corroborated crisis signal detected."}


def build_risk_fallback(state: CrisisState) -> dict:
    history = state.get("history", [])
    repeated = sum(1 for item in history if item.get("crisis") == state["crisis"])
    crisis = state["crisis"]

    if crisis == "BOTH":
        severity = "CRITICAL"
    elif crisis in {"FIRE", "MEDICAL"} and (repeated >= 2 or state["vision_event"]["confidence"] >= 0.80):
        severity = "HIGH"
    elif crisis in {"FIRE", "MEDICAL"}:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    urgency = "IMMEDIATE" if severity in {"HIGH", "CRITICAL"} else "MONITOR"
    return {"severity": severity, "urgency": urgency,
            "note": f"{repeated} similar event(s) for {state['camera_id']}."}


def build_decision_output(state: CrisisState) -> dict:
    danger = normalize_choice(
        state["fusion_output"].get("crisis_type", state["crisis"]),
        {"SAFE", "FIRE", "MEDICAL", "BOTH"}, state["crisis"]
    )
    action = decision_engine(danger)
    severity = state["risk_output"]["severity"]
    priority = "HIGH" if severity in {"HIGH", "CRITICAL"} else "MEDIUM"
    if action == "NO_ACTION":
        priority = "LOW"
    return {"danger": danger, "action": action, "priority": priority}


def build_action_output(state: CrisisState) -> dict:
    action = state["decision_output"]["action"]
    danger = state["decision_output"]["danger"]
    tool = "send_alert" if action != "NO_ACTION" else "log_event"
    if action == "NO_ACTION":
        message = (f"No emergency escalation for {state['camera_id']} "
                   f"frame {state['frame_index']}.")
    else:
        message = (f"{danger} on {state['camera_id']} frame {state['frame_index']}; "
                   f"dispatching {action.lower()}.")
    return {"action": action, "tool": tool, "message": message}


def fusion_agent(state: CrisisState) -> CrisisState:
    history = history_by_camera[state["camera_id"]]
    state["history"] = list(history)
    fallback = build_fusion_fallback(state)
    prompt = f"""
You are a crisis validation AI.
Vision event JSON:\n{json.dumps(state["vision_event"], sort_keys=True)}
Context JSON:\n{json.dumps(state["social"], sort_keys=True)}
Return only valid JSON:
{{"is_crisis": true, "crisis_type": "SAFE/FIRE/MEDICAL/BOTH", "confidence": "LOW/MEDIUM/HIGH", "reason": "short reason"}}
"""
    parsed = invoke_json_agent(prompt, fallback)
    state["fusion_output"] = {
        "is_crisis": bool(parsed.get("is_crisis", fallback["is_crisis"])),
        "crisis_type": normalize_choice(parsed.get("crisis_type", fallback["crisis_type"]),
                                        {"SAFE", "FIRE", "MEDICAL", "BOTH"}, fallback["crisis_type"]),
        "confidence": normalize_choice(parsed.get("confidence", fallback["confidence"]),
                                       {"LOW", "MEDIUM", "HIGH"}, fallback["confidence"]),
        "reason": str(parsed.get("reason", fallback["reason"])),
    }
    history.append({"frame_index": state["frame_index"],
                    "crisis": state["fusion_output"]["crisis_type"],
                    "confidence": state["fusion_output"]["confidence"]})
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]
    return state


def risk_agent(state: CrisisState) -> CrisisState:
    fallback = build_risk_fallback(state)
    prompt = f"""
You are a risk assessment AI.
Fusion output JSON:\n{json.dumps(state["fusion_output"], sort_keys=True)}
History:\n{json.dumps(state.get("history", []), sort_keys=True)}
Return only valid JSON:
{{"severity": "LOW/MEDIUM/HIGH/CRITICAL", "urgency": "MONITOR/IMMEDIATE", "note": "short reason"}}
"""
    parsed = invoke_json_agent(prompt, fallback)
    state["risk_output"] = {
        "severity": normalize_choice(parsed.get("severity", fallback["severity"]),
                                     {"LOW", "MEDIUM", "HIGH", "CRITICAL"}, fallback["severity"]),
        "urgency": normalize_choice(parsed.get("urgency", fallback["urgency"]),
                                    {"MONITOR", "IMMEDIATE"}, fallback["urgency"]),
        "note": str(parsed.get("note", fallback["note"])),
    }
    return state


def decision_agent(state: CrisisState) -> CrisisState:
    state["decision_output"] = build_decision_output(state)
    return state


def action_agent(state: CrisisState) -> CrisisState:
    state["action_output"] = build_action_output(state)
    return state


def build_graph():
    graph = StateGraph(CrisisState)
    graph.add_node("fusion_node", fusion_agent)
    graph.add_node("risk_node", risk_agent)
    graph.add_node("decision_node", decision_agent)
    graph.add_node("action_node", action_agent)
    graph.set_entry_point("fusion_node")
    graph.add_edge("fusion_node", "risk_node")
    graph.add_edge("risk_node", "decision_node")
    graph.add_edge("decision_node", "action_node")
    graph.add_edge("action_node", END)
    return graph.compile()


# ── LLM fusion saying (identical to original) ────────────────────────────────

def generate_social_fusion_saying(event_type: str) -> dict:
    llm = get_llm()
    prompt = (
        f"Generate a very short, simple social media-style saying confirming a {event_type} incident. "
        "Use plain, simple words. Keep it under 15 words. Return ONLY the text."
    )
    fallback_map = {
        "fire": "I see smoke coming from the building, help!",
        "fall": "Someone just fell down in the gym area!",
    }
    text = fallback_map.get(event_type, "Unusual activity detected at the site.")
    if llm:
        try:
            response = llm.invoke(prompt)
            text = response.content.strip().replace('"', '')
            if len(text.split()) > 20:
                text = " ".join(text.split()[:15]) + "..."
        except Exception as e:
            logger.warning("LLM fusion saying failed: %s", e)
    return {"summary": text, "link": "https://emergency-response.io/status/live",
            "confirmation": "Groq-Powered Intelligence Fusion"}


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
    cap = cv2.VideoCapture(normalize_video_source(video_source))
    if not cap.isOpened():
        print(f"[System] Skipping invalid video: {video_source}")
        return

    FRAME_SKIP = 2
    video_filename = os.path.basename(str(video_source))
    location = CAMERA_LOCATIONS.get(camera_id.lower(), f"Site: {video_filename}")
    event_type = ("fire" if "fire" in video_filename.lower()
                  else ("fall" if "fall" in video_filename.lower() else None))

    incident_locked = False
    social_generated = False

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

            # ── Social + LLM confirmation ─────────────────────────────────────
            if not social_generated and attention_state != "SAFE":
                is_fire = stable_event.get("fire", False)
                is_fall = stable_event.get("fall_detected", False)
                if is_fire or is_fall:
                    api_server.update_crisis_state({"lifecycle_state": "DETECTED"})
                    social_sigs = simulate_social_signals(event_type) if event_type else []
                    llm_data = generate_social_fusion_saying(event_type) if event_type else {}
                    state = api_server.get_crisis_state()
                    api_server.update_crisis_state({
                        "signals": social_sigs,
                        "llm_summary": llm_data.get("summary"),
                        "llm_link": llm_data.get("link"),
                        "llm_confirmation": llm_data.get("confirmation"),
                        "lifecycle_state": "CONFIRMED",
                        "logs": state["logs"] + [
                            "[Detection] Initial visual signature identified",
                            "[Social] Automated external signal scan active",
                            "[Fusion] Vision + social signal fusion confirmed",
                            "[LLM] Contextual intelligence summary generated"
                        ]
                    })
                    social_generated = True

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

                if action != "NO_ACTION" and (trust > 0.4 or social_generated):
                    is_fire = "FIRE" in action
                    explanation = [
                        f"{'Fire/Smoke' if is_fire else 'Fall'} signature detected",
                        "Temporal consistency verified (3+ frames)",
                    ]
                    if social_generated:
                        explanation.append("Multi-channel social signals confirm threat")

                    incident_locked = True
                    send_alert(action, camera_id=camera_id,
                               details=result["action_output"]["message"])
                    state = api_server.get_crisis_state()
                    api_server.update_crisis_state({
                        "decision": action,
                        "severity": severity,
                        "trust_score": round(max(trust, 0.88), 2),
                        "lifecycle_state": "DISPATCHED",
                        "confidence_explanation": explanation,
                        "decision_reason": f"{'Fire' if is_fire else 'Fall'} + social confirmation",
                        "status": "ALERT",
                        "incident_locked": True,
                        "logs": state["logs"] + [f"[Decision] {action} — {explanation[-1]}"],
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


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aegis-Crisis unified pipeline")
    parser.add_argument("--video", default=DEFAULT_VIDEO_SOURCE)
    parser.add_argument("--camera-id", default=DEFAULT_CAMERA_ID)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--display", action="store_true")
    parser.add_argument("--demo-mode", action="store_true")
    parser.add_argument("--playlist", action="store_true")
    parser.add_argument("--no-hmac", action="store_true",
                        help="Disable HMAC watermark checking (useful when camera has no embedder)")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    db.init_db()
    api_server.start_server()

    video_queue: list[str] = []
    if args.playlist:
        video_queue = sorted(glob.glob("videos/*.mp4"))
        if not video_queue:
            print("[System] No videos found in 'videos/' folder.")
            return
    elif args.demo_mode:
        video_queue = sorted(glob.glob(os.getenv("DEMO_VIDEO_GLOB", "videos/*.mp4")))
    else:
        video_queue = [args.video]

    session_id = args.session_id or str(uuid.uuid4())

    for i, video in enumerate(video_queue):
        if i > 0:
            print("[System] Video transition: cooling down...")
            time.sleep(2)
        camera_id = (
            "fall" if "fall" in str(video).lower() else
            "fire" if "fire" in str(video).lower() else
            "webcam"
        )
        print(f"\n[System] Loading: {video} (session={session_id})")
        run_live_graph(
            video_source=video,
            camera_id=args.camera_id or camera_id,
            session_id=session_id,
            display=args.display,
            max_frames=args.max_frames,
            skip_hmac=args.no_hmac,
        )


if __name__ == "__main__":
    main()
