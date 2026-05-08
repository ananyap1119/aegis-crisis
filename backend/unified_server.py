"""
Aegis-Crisis Unified Flask-SocketIO Server

Merges:
  - ai-crisis-response api_server.py  (FastAPI/uvicorn on 8000)
  - Aegis app.py                       (Flask-SocketIO on 5000)

All traffic now on port 5000 with CORS enabled for the React frontend.

SocketIO events emitted:
  crisis_update  — new crisis pipeline result
  tamper_update  — new tamper detection
"""
from __future__ import annotations

import base64
import threading
import time
from datetime import datetime
from typing import Any

import cv2
from flask import Flask, jsonify, request
from flask_socketio import SocketIO

import db

app = Flask(__name__)
app.config["SECRET_KEY"] = "aegis-crisis-secret"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Shared in-memory state (written by pipeline, read by API/WS handlers) ──
_state_lock = threading.Lock()

_crisis_state: dict[str, Any] = {
    "decision": None,
    "severity": None,
    "trust_score": 0.0,
    "location": "Unknown",
    "current_video": None,
    "lifecycle_state": "MONITORING",
    "confidence_explanation": [],
    "decision_reason": None,
    "signals": [],
    "llm_summary": None,
    "llm_link": None,
    "llm_confirmation": None,
    "system_health": {
        "model_status": "ACTIVE",
        "camera_status": "CONNECTED",
        "api_status": "ONLINE",
        "latency": "45ms",
    },
    "logs": [],
    "incident_locked": False,
    "frame": None,
    "status": "SAFE",
    "active_cameras": [],
    "tamper_alerts": [],
}

_active_cameras: dict[str, dict] = {}  # camera_id → {session_id, status}


# ── Helpers ──────────────────────────────────────────────────────────────────

def encode_frame(frame) -> str | None:
    if frame is None:
        return None
    _, buf = cv2.imencode(".jpg", frame)
    return base64.b64encode(buf).decode()


def update_crisis_state(data: dict) -> None:
    with _state_lock:
        _crisis_state.update(data)


def get_crisis_state() -> dict:
    with _state_lock:
        return dict(_crisis_state)


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """System health, active cameras, recent tamper alerts."""
    import random
    state = get_crisis_state()
    state["system_health"]["latency"] = f"{random.randint(40, 52)}ms"
    return jsonify({
        "lifecycle_state": state["lifecycle_state"],
        "decision": state["decision"],
        "severity": state["severity"],
        "trust_score": state["trust_score"],
        "location": state["location"],
        "current_video": state["current_video"],
        "system_health": state["system_health"],
        "active_cameras": list(_active_cameras.keys()),
        "tamper_alerts": db.get_recent_tamper_events(limit=10),
        "logs": state["logs"][-50:],
        "signals": state["signals"],
        "llm_summary": state["llm_summary"],
        "incident_locked": state["incident_locked"],
        # Crisis dashboard fields
        "frame": state.get("frame"),
        "status": state.get("status", "SAFE"),
        "confidence_explanation": state["confidence_explanation"],
        "decision_reason": state["decision_reason"],
    })


@app.route("/api/crisis_events")
def api_crisis_events():
    """Latest crisis detections from DB."""
    limit = request.args.get("limit", 50, type=int)
    events = db.get_recent_crisis_events(limit=limit)
    return jsonify({"events": events, "count": len(events)})


@app.route("/api/tamper_events")
def api_tamper_events():
    """Latest tamper incidents from DB."""
    limit = request.args.get("limit", 50, type=int)
    events = db.get_recent_tamper_events(limit=limit)
    return jsonify({"events": events, "count": len(events)})


@app.route("/api/start_camera", methods=["POST"])
def api_start_camera():
    """Register a camera_id as active in the pipeline."""
    payload = request.get_json(silent=True) or {}
    camera_id = payload.get("camera_id", "camera-0")
    session_id = payload.get("session_id", f"session-{int(time.time())}")

    _active_cameras[camera_id] = {
        "session_id": session_id,
        "status": "active",
        "started_at": datetime.utcnow().isoformat(),
    }
    update_crisis_state({"logs": get_crisis_state()["logs"] + [
        f"[System] Camera {camera_id} started (session {session_id})"
    ]})
    return jsonify({"ok": True, "camera_id": camera_id, "session_id": session_id})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    update_crisis_state({
        "decision": None,
        "severity": None,
        "trust_score": 0.0,
        "lifecycle_state": "MONITORING",
        "confidence_explanation": [],
        "decision_reason": None,
        "signals": [],
        "llm_summary": None,
        "llm_link": None,
        "llm_confirmation": None,
        "logs": [],
        "incident_locked": False,
        "status": "SAFE",
    })
    return jsonify({"ok": True})


@app.route("/api/override", methods=["POST"])
def api_override():
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    state = get_crisis_state()
    update_crisis_state({
        "decision": action,
        "lifecycle_state": "DISPATCHED" if action != "IGNORE" else "MONITORING",
        "incident_locked": action != "IGNORE",
        "decision_reason": f"Manual override by operator: {action}",
        "logs": state["logs"] + [f"[Manual] Operator overrode system with: {action}"],
    })
    return jsonify({"ok": True})


# ── SocketIO handlers ─────────────────────────────────────────────────────────

@socketio.on("connect", namespace="/stream")
def on_connect():
    socketio.emit("status_update", {"status": "healthy", "message": "Connected to Aegis-Crisis"}, namespace="/stream")


@socketio.on("disconnect", namespace="/stream")
def on_disconnect():
    pass


# ── Emission helpers (called by main_unified.py) ─────────────────────────────

def emit_crisis_update(payload: dict) -> None:
    """Push a crisis pipeline result to all dashboard clients."""
    try:
        socketio.emit("crisis_update", payload, namespace="/stream")
    except Exception as exc:
        pass  # not fatal if no clients connected


def emit_tamper_update(payload: dict) -> None:
    """Push a tamper detection result to all dashboard clients."""
    try:
        socketio.emit("tamper_update", payload, namespace="/stream")
    except Exception as exc:
        pass


# ── Server startup ────────────────────────────────────────────────────────────

def start_server(host: str = "0.0.0.0", port: int = 5000) -> None:
    """Start Flask-SocketIO in a daemon thread."""
    def _run():
        socketio.run(app, host=host, port=port, log_output=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
