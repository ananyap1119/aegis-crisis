from __future__ import annotations

import json
import logging
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

import cv2
from dotenv import load_dotenv


load_dotenv()

DEFAULT_CAMERA_ID = "camera-0"
DEFAULT_LOG_LEVEL = "INFO"


def get_env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


class VisionEvent(TypedDict):
    camera_id: str
    frame_index: int
    fire: bool
    smoke: bool
    person: bool
    fall_detected: bool
    confidence: float
    fire_confidence: float
    smoke_confidence: float
    raw_fire_detected: bool
    raw_smoke_detected: bool
    motion_score: float
    temporal_fire_average: float
    temporal_smoke_average: float
    temporal_fire_support: int
    validation_state: str
    validation_reason: str
    # Tamper integrity fields added by tamper_agent before crisis pipeline
    tamper_status: bool
    tamper_reason: str


class SocialSignal(TypedDict):
    type: str
    confidence: float
    source: str
    text: str
    location: str


class FusionOutput(TypedDict):
    is_crisis: bool
    crisis_type: str
    confidence: str
    reason: str


class RiskOutput(TypedDict):
    severity: str
    urgency: str
    note: str


class DecisionOutput(TypedDict):
    danger: str
    action: str
    priority: str


class ActionOutput(TypedDict):
    action: str
    tool: str
    message: str


class CrisisState(TypedDict, total=False):
    camera_id: str
    frame_index: int
    vision_event: VisionEvent
    social: SocialSignal
    crisis: str
    fusion_output: FusionOutput
    risk_output: RiskOutput
    decision_output: DecisionOutput
    action_output: ActionOutput
    history: list[dict]


@dataclass
class CameraRuntimeState:
    fire_history: deque[float] = field(default_factory=deque)
    smoke_history: deque[float] = field(default_factory=deque)
    fall_history: deque[float] = field(default_factory=deque)
    previous_gray: Any | None = None
    last_action: str = "NO_ACTION"
    last_attention_state: str = "SAFE"


def configure_logging(level: str = DEFAULT_LOG_LEVEL) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_payload(logger: logging.Logger, level: int, event_name: str, payload: dict) -> None:
    logger.log(level, "%s %s", event_name, json.dumps(payload, sort_keys=True))


def create_vision_event(camera_id: str = DEFAULT_CAMERA_ID, frame_index: int = 0) -> VisionEvent:
    return {
        "camera_id": camera_id,
        "frame_index": frame_index,
        "fire": False,
        "smoke": False,
        "person": False,
        "fall_detected": False,
        "confidence": 0.0,
        "fire_confidence": 0.0,
        "smoke_confidence": 0.0,
        "raw_fire_detected": False,
        "raw_smoke_detected": False,
        "motion_score": 0.0,
        "temporal_fire_average": 0.0,
        "temporal_smoke_average": 0.0,
        "temporal_fire_support": 0,
        "validation_state": "SAFE",
        "validation_reason": "no_signal",
        "tamper_status": False,
        "tamper_reason": "",
    }


def normalize_video_source(source: str) -> int | str:
    return int(source) if source.isdigit() else source


class TemporalEventTracker:
    def __init__(self, stability_frames: int = 3):
        self.stability_frames = stability_frames
        self.fire_threshold = get_env_float("FIRE_THRESHOLD", 0.75)
        self.smoke_threshold = get_env_float("SMOKE_THRESHOLD", 0.60)
        self.motion_threshold = get_env_float("MOTION_THRESHOLD", 0.02)
        self.fire_temporal_window = get_env_int("TEMPORAL_WINDOW", 5)
        self.fire_temporal_min_frames = get_env_int("TEMPORAL_MIN_HITS", 3)
        self.fall_temporal_window = get_env_int("FALL_TEMPORAL_WINDOW", max(3, stability_frames))
        self.fall_temporal_min_frames = get_env_int(
            "FALL_TEMPORAL_MIN_FRAMES",
            min(self.fall_temporal_window, stability_frames),
        )
        self.monitor_factor = get_env_float("MONITOR_FIRE_FACTOR", 0.75)
        self.debug_save_fire_frames = get_env_bool("DEBUG_SAVE_FIRE_FRAMES", False)
        self.debug_frame_dir = Path(os.getenv("DEBUG_FRAME_DIR", "debug_fire_frames"))
        self._states: dict[str, CameraRuntimeState] = {}

    def get_state(self, camera_id: str) -> CameraRuntimeState:
        state = self._states.get(camera_id)
        if state is None:
            state = CameraRuntimeState(
                fire_history=deque(maxlen=self.fire_temporal_window),
                smoke_history=deque(maxlen=self.fire_temporal_window),
                fall_history=deque(maxlen=self.fall_temporal_window),
            )
            self._states[camera_id] = state
        return state

    def _compute_motion_score(self, state: CameraRuntimeState, frame) -> float:
        if frame is None:
            return 0.0

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if state.previous_gray is None:
            state.previous_gray = gray
            return 0.0

        diff = cv2.absdiff(gray, state.previous_gray)
        state.previous_gray = gray
        return float(cv2.mean(diff)[0])

    def _average(self, values: deque[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _sanitize_reason(self, reason: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", reason.strip().lower()).strip("_")
        return sanitized or "debug"

    def _save_debug_frame(self, frame, event: VisionEvent, state: str, reason: str) -> None:
        if frame is None or not self.debug_save_fire_frames:
            return

        self.debug_frame_dir.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{event['camera_id']}_frame_{event['frame_index']:06d}_"
            f"{state.lower()}_{self._sanitize_reason(reason)}.jpg"
        )
        cv2.imwrite(str(self.debug_frame_dir / filename), frame)

    def stabilize(self, event: VisionEvent, frame=None) -> VisionEvent:
        state = self.get_state(event["camera_id"])

        raw_fire_detected = bool(event["fire"])
        raw_smoke_detected = bool(event["smoke"])
        motion_score = self._compute_motion_score(state, frame)

        state.fire_history.append(float(event["fire_confidence"]))
        state.smoke_history.append(float(event["smoke_confidence"]))
        state.fall_history.append(1.0 if event["fall_detected"] else 0.0)

        rolling_fire_average = self._average(state.fire_history)
        rolling_smoke_average = self._average(state.smoke_history)
        fire_support = sum(conf >= self.fire_threshold for conf in state.fire_history)
        validated_fall = sum(state.fall_history) >= self.fall_temporal_min_frames

        motion_ok = motion_score >= self.motion_threshold
        smoke_supported = (
            event["smoke_confidence"] >= self.smoke_threshold
            or rolling_smoke_average >= self.smoke_threshold
        )
        temporal_supported = (
            fire_support >= self.fire_temporal_min_frames
            and rolling_fire_average >= self.fire_threshold
        )
        weak_fire_signal = (
            raw_fire_detected
            or raw_smoke_detected
            or rolling_fire_average >= self.fire_threshold * self.monitor_factor
        )

        validation_state = "SAFE"
        validation_reason = "no validated fire signal"
        validated_fire = False
        validated_smoke = False

        if raw_fire_detected and not motion_ok:
            validation_reason = f"low motion ({motion_score:.2f} < {self.motion_threshold:.2f})"
        elif raw_fire_detected and motion_ok:
            if smoke_supported:
                validated_fire = True
                validated_smoke = True
                validation_state = "ALERT"
                validation_reason = "fire + smoke confirmation"
            elif temporal_supported:
                validated_fire = True
                validation_state = "ALERT"
                validation_reason = f"temporal consistency {fire_support}/{self.fire_temporal_window}"
            else:
                validation_state = "MONITOR"
                validation_reason = f"no smoke support; temporal {fire_support}/{self.fire_temporal_min_frames}"
        elif weak_fire_signal and motion_ok:
            validation_state = "MONITOR"
            if raw_smoke_detected and not raw_fire_detected:
                validation_reason = "smoke without fire confirmation"
            else:
                validation_reason = "weak fire signal"

        stable_event = event.copy()
        stable_event["raw_fire_detected"] = raw_fire_detected
        stable_event["raw_smoke_detected"] = raw_smoke_detected
        stable_event["fire"] = validated_fire
        stable_event["smoke"] = validated_smoke
        stable_event["fall_detected"] = validated_fall
        stable_event["motion_score"] = motion_score
        stable_event["temporal_fire_average"] = rolling_fire_average
        stable_event["temporal_smoke_average"] = rolling_smoke_average
        stable_event["temporal_fire_support"] = fire_support
        stable_event["validation_state"] = validation_state
        stable_event["validation_reason"] = validation_reason
        stable_event["confidence"] = max(
            stable_event["confidence"],
            rolling_fire_average,
            rolling_smoke_average,
        )

        if raw_fire_detected or raw_smoke_detected or validation_state != "SAFE":
            self._save_debug_frame(frame, stable_event, validation_state, validation_reason)

        return stable_event

    def should_invoke_graph(self, camera_id: str, attention_state: str) -> bool:
        state = self.get_state(camera_id)
        changed = attention_state != state.last_attention_state
        state.last_attention_state = attention_state
        if attention_state == "SAFE":
            state.last_action = "NO_ACTION"
            return False
        return changed

    def should_send_alert(self, camera_id: str, action: str) -> bool:
        state = self.get_state(camera_id)
        should_send = action != "NO_ACTION" and action != state.last_action
        state.last_action = action
        return should_send
