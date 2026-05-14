"""
SecureEye — Gate 1 Fall Watch Window

After a fall is detected by YOLO, a watch window of WATCH_SECONDS is opened.
During this window the system observes whether the person recovers:

  Person gets up within WATCH_SECONDS    → suppress (not a health emergency)
  Person motionless after WATCH_SECONDS  → escalate to Gate 2
  Person struggling but can't rise       → escalate to Gate 2 early

State machine per camera:
  IDLE       — no fall in progress
  WATCHING   — fall detected; counting frames
  ESCALATE   — watch window expired or early-escalation triggered
  SUPPRESSED — person recovered; reset to IDLE next detection

Fall posture is inferred from YOLOv8 bounding-box aspect ratio and position:
  - Wide flat box at low Y → likely horizontal (on ground)
  - Bounding box centre of mass below mid-frame → likely fallen

(Full pose-keypoint estimation requires yolov8n-pose.pt; aspect-ratio heuristic
 is used here so the gate works with the standard yolov8n model.)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

FallState = Literal["IDLE", "WATCHING", "ESCALATE", "SUPPRESSED"]

WATCH_SECONDS       = 9.0    # observation window
EARLY_ESCALATE_CONF = 0.85   # if fall confidence stays above this, escalate early
ASPECT_FALLEN_MAX   = 0.6    # width/height ratio — > this suggests horizontal posture
RECOVERY_ASPECT_MIN = 1.2    # below this ratio = upright again


@dataclass
class _CameraState:
    state:           FallState = "IDLE"
    fall_start_time: float     = 0.0
    fall_confidence: float     = 0.0
    max_confidence:  float     = 0.0
    frames_fallen:   int       = 0
    frames_upright:  int       = 0


_cameras: dict[str, _CameraState] = {}


def _get(camera_id: str) -> _CameraState:
    if camera_id not in _cameras:
        _cameras[camera_id] = _CameraState()
    return _cameras[camera_id]


def _is_upright(person_box: tuple[int, int, int, int] | None) -> bool:
    if person_box is None:
        return True
    x1, y1, x2, y2 = person_box
    w, h = x2 - x1, y2 - y1
    if h == 0:
        return True
    aspect = w / h
    return aspect < ASPECT_FALLEN_MAX


def evaluate(
    camera_id: str,
    fall_detected: bool,
    fall_confidence: float = 0.0,
    person_box: tuple[int, int, int, int] | None = None,
) -> tuple[FallState, dict]:
    """
    Update fall state machine and return (state, details).

    Call once per frame for each camera.
    Returns 'ESCALATE' when Gate 2 review is needed.
    """
    cam = _get(camera_id)
    now = time.monotonic()
    upright = _is_upright(person_box)

    if cam.state == "IDLE":
        if fall_detected:
            cam.state           = "WATCHING"
            cam.fall_start_time = now
            cam.fall_confidence = fall_confidence
            cam.max_confidence  = fall_confidence
            cam.frames_fallen   = 1
            cam.frames_upright  = 0
            logger.info("Gate1Fall[WATCHING] cam=%s conf=%.2f", camera_id, fall_confidence)

    elif cam.state == "WATCHING":
        elapsed = now - cam.fall_start_time

        if fall_detected:
            cam.frames_fallen  += 1
            cam.max_confidence  = max(cam.max_confidence, fall_confidence)

        if upright:
            cam.frames_upright += 1
        else:
            cam.frames_upright  = 0

        # Recovery: upright for 3+ consecutive frames
        if cam.frames_upright >= 3:
            cam.state = "SUPPRESSED"
            logger.info("Gate1Fall[SUPPRESSED] cam=%s — person recovered", camera_id)

        # Early escalation: very confident fall, person still down
        elif cam.max_confidence >= EARLY_ESCALATE_CONF and not upright and elapsed > 3.0:
            cam.state = "ESCALATE"
            logger.warning("Gate1Fall[ESCALATE early] cam=%s conf=%.2f", camera_id, cam.max_confidence)

        # Watch window expired
        elif elapsed >= WATCH_SECONDS:
            cam.state = "ESCALATE"
            logger.warning("Gate1Fall[ESCALATE timeout] cam=%s elapsed=%.1fs", camera_id, elapsed)

    elif cam.state in ("ESCALATE", "SUPPRESSED"):
        # Stay in terminal state until reset
        pass

    details = {
        "state":          cam.state,
        "elapsed_s":      round(now - cam.fall_start_time, 1) if cam.fall_start_time else 0,
        "max_confidence": round(cam.max_confidence, 3),
        "frames_fallen":  cam.frames_fallen,
        "frames_upright": cam.frames_upright,
    }

    return cam.state, details


def reset_camera(camera_id: str) -> None:
    _cameras.pop(camera_id, None)
