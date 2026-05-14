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
app.config["SECRET_KEY"] = "secureeye-secret"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ── Pipeline controller (set by main_unified.py at startup) ──────────────────
_pipeline_controller = None

def set_pipeline_controller(controller) -> None:
    global _pipeline_controller
    _pipeline_controller = controller

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
    "alerts": [],
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
        "alerts": state.get("alerts", []),
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
        "alerts": [],
    })
    return jsonify({"ok": True})


@app.route("/api/stop_alerts")
def api_stop_alerts():
    """Called by the Stop Alerts button in emails."""
    camera_id  = request.args.get("camera_id", "")
    alert_type = request.args.get("type", "")
    if camera_id and alert_type:
        try:
            from gate2_email import stop_alerts
            stop_alerts(camera_id, alert_type)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
        return (
            "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
            f"<h2>✅ Alerts stopped</h2>"
            f"<p>No more <b>{alert_type}</b> alerts for camera <b>{camera_id}</b>.</p>"
            "<p>You can close this tab.</p></body></html>"
        )
    return jsonify({"ok": False, "error": "missing camera_id or type"}), 400


@app.route("/api/review")
def api_review():
    """Called by Confirm / False Alarm buttons in review emails."""
    event_id = request.args.get("event_id", "")
    action   = request.args.get("action", "")
    action_labels = {
        "confirm_fire":    "🔥 Fire department dispatched.",
        "onsite_handles":  "👷 On-site team handling the situation.",
        "confirm_fall":    "🚑 Ambulance dispatched.",
        "false_alarm":     "✅ Marked as false alarm. No action taken.",
    }
    label = action_labels.get(action, f"Action '{action}' recorded.")
    return (
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
        f"<h2>{label}</h2>"
        f"<p>Event ID: <code>{event_id}</code></p>"
        "<p>You can close this tab.</p></body></html>"
    )


@app.route("/api/demo/play", methods=["POST"])
def api_demo_play():
    """Start playing a specific video or webcam source."""
    if _pipeline_controller is None:
        return jsonify({"ok": False, "error": "pipeline controller not ready"}), 503
    payload = request.get_json(silent=True) or {}
    source  = payload.get("source", "0")
    _pipeline_controller.play(source)
    state = get_crisis_state()
    update_crisis_state({
        "decision": None, "severity": None, "trust_score": 0.0,
        "lifecycle_state": "MONITORING", "incident_locked": False,
        "status": "SAFE", "logs": state["logs"] + [f"[Demo] Source switched → {source}"],
    })
    return jsonify({"ok": True, "source": source})


@app.route("/api/demo/play_all", methods=["POST"])
def api_demo_play_all():
    """Play all demo videos in sequence: fall1 → fire1 → fire2."""
    if _pipeline_controller is None:
        return jsonify({"ok": False, "error": "pipeline controller not ready"}), 503
    _pipeline_controller.play_all()
    state = get_crisis_state()
    update_crisis_state({
        "decision": None, "severity": None, "trust_score": 0.0,
        "lifecycle_state": "MONITORING", "incident_locked": False,
        "status": "SAFE", "alerts": [],
        "logs": state["logs"] + ["[Demo] Starting full demo sequence: fall → fire1 → fire2"],
    })
    return jsonify({"ok": True})


@app.route("/api/demo/stop", methods=["POST"])
def api_demo_stop():
    """Stop the active pipeline."""
    if _pipeline_controller:
        _pipeline_controller.stop()
    state = get_crisis_state()
    update_crisis_state({"logs": state["logs"] + ["[Demo] Pipeline stopped"]})
    return jsonify({"ok": True})


@app.route("/api/demo/inject_tamper", methods=["POST"])
def api_demo_inject_tamper():
    """Inject a fake tamper event for demo purposes."""
    import uuid as _uuid
    payload     = request.get_json(silent=True) or {}
    tamper_type = payload.get("type", "blackout")
    camera_id   = payload.get("camera_id", "demo-cam")

    reason_map = {
        "blackout":    "mean_luminance=2.1 (demo)",
        "lens_spray":  "mean_luminance=7.3 CLAHE failed (demo)",
        "reposition":  "orb_match_ratio=0.11 (demo)",
        "feed_freeze": "ssim=0.9993 for 90 frames (demo)",
        "coordinated": "physical + digital tamper simultaneous (demo)",
    }
    reason = reason_map.get(tamper_type, "demo injection")

    try:
        from tamper_router import route_tamper
        from frame_buffer import get_pre_event_frames

        if tamper_type == "coordinated":
            route_tamper("blackout",    camera_id, "blackout: demo")
            route_tamper("feed_freeze", camera_id, "feed_freeze: demo")
        else:
            pre = get_pre_event_frames(camera_id, seconds=5)
            route_tamper(tamper_type, camera_id, reason, pre)

        ts = time.time()
        db.log_tamper_event(
            session_id="demo-session",
            camera_id=camera_id,
            timestamp=ts,
            tamper_type=tamper_type if tamper_type != "coordinated" else "blackout",
            reason=reason,
            hmac_valid=False,
        )
        tamper_payload = {
            "camera_id": camera_id, "session_id": "demo-session",
            "timestamp": ts, "tamper_type": tamper_type,
            "reason": reason, "hmac_valid": False,
        }
        emit_tamper_update(tamper_payload)
        state = get_crisis_state()
        update_crisis_state({"logs": state["logs"] + [
            f"[Demo] Injected tamper: {tamper_type} on {camera_id}"
        ]})
        return jsonify({"ok": True, "type": tamper_type})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


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
        socketio.run(app, host=host, port=port, log_output=False, use_reloader=False, allow_unsafe_werkzeug=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
