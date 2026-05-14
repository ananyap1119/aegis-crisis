"""
SecureEye — Gate 1 Fire Pre-screen

Three signals are computed per detection event to filter YOLO false positives
before any human is involved:

  1. Flicker variance  — real fire pixels change chaotically across frames.
                         Static red objects (lights, signs) don't.
                         Score 0–1; real fire typically > 0.3.

  2. Bounding-box growth — fire spreads; its bounding box area increases.
                           Growth rate > 15% over 5 frames = real fire.

  3. Smoke correlation — if fire is detected with zero smoke after 20 seconds,
                         confidence drops (most real fires produce smoke).

Composite score maps to one of three tiers:

  TIER_1  (score < 0.4)  — watch 10 more seconds, suppress if resolved
  TIER_2  (score < 0.75) — confirmed; generate clip, send to Gate 2 human review
  TIER_3  (score >= 0.75) — fast-growing / multi-camera; bypass Gate 2, dispatch now
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Literal

import cv2
import numpy as np

logger = logging.getLogger(__name__)

FireTier = Literal["TIER_1", "TIER_2", "TIER_3", "SAFE"]

# Tuning constants
FLICKER_WINDOW       = 10     # frames to measure temporal variance
BBOX_GROWTH_WINDOW   = 5      # frames to measure area growth
BBOX_GROWTH_RATE     = 0.15   # 15 % area increase over window = spreading
SMOKE_WAIT_FRAMES    = 600    # ~20 s at 30 fps before smoke absence penalises
FLICKER_REAL_FIRE    = 0.30   # above this variance = real fire signal

# Per-camera histories
_pixel_histories: dict[str, deque[np.ndarray]] = {}   # grayscale ROI crops
_bbox_areas:      dict[str, deque[float]]       = {}   # bounding box areas
_fire_frame_count: dict[str, int]               = {}   # consecutive fire frames
_smoke_seen:       dict[str, bool]              = {}   # has smoke been seen?


def _roi_crop(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = box
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    crop = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    return cv2.resize(crop, (32, 32))


def _flicker_score(camera_id: str, roi: np.ndarray) -> float:
    """Temporal pixel variance across FLICKER_WINDOW ROI crops, normalised 0–1."""
    history = _pixel_histories.setdefault(camera_id, deque(maxlen=FLICKER_WINDOW))
    history.append(roi.astype(np.float32))

    if len(history) < 3:
        return 0.0

    stack = np.stack(history, axis=0)          # (T, 32, 32)
    var   = float(np.mean(np.var(stack, axis=0)))
    # Typical real-fire variance ~200-800; normalise with soft cap at 1000
    return min(var / 1000.0, 1.0)


def _growth_score(camera_id: str, area: float) -> float:
    """Fractional area growth over BBOX_GROWTH_WINDOW frames."""
    history = _bbox_areas.setdefault(camera_id, deque(maxlen=BBOX_GROWTH_WINDOW))
    history.append(area)

    if len(history) < BBOX_GROWTH_WINDOW:
        return 0.0

    oldest = history[0]
    if oldest < 1.0:
        return 0.0

    growth = (history[-1] - oldest) / oldest
    return min(max(growth, 0.0), 1.0)   # clamp 0–1


def evaluate(
    frame: np.ndarray,
    camera_id: str,
    fire_box: tuple[int, int, int, int] | None,
    smoke_detected: bool,
    fire_confidence: float = 0.0,
) -> tuple[FireTier, float, dict]:
    """
    Evaluate a single frame and return (tier, composite_score, details).

    fire_box: (x1, y1, x2, y2) bounding box of the fire detection, or None.
    smoke_detected: whether the vision agent also detected smoke this frame.
    fire_confidence: raw YOLO confidence for the fire class.
    """
    if fire_box is None:
        # No detection — reset counters and return safe
        _fire_frame_count[camera_id] = 0
        return "SAFE", 0.0, {"reason": "no_fire_detected"}

    _fire_frame_count[camera_id] = _fire_frame_count.get(camera_id, 0) + 1

    if smoke_detected:
        _smoke_seen[camera_id] = True

    x1, y1, x2, y2 = fire_box
    area = max(0.0, float((x2 - x1) * (y2 - y1)))

    roi            = _roi_crop(frame, fire_box)
    flicker        = _flicker_score(camera_id, roi)
    growth         = _growth_score(camera_id, area)

    # Smoke correlation penalty after 20 s without smoke
    fire_frames = _fire_frame_count[camera_id]
    smoke_ok    = _smoke_seen.get(camera_id, False) or fire_frames < SMOKE_WAIT_FRAMES
    smoke_bonus = 0.15 if smoke_ok else -0.10

    composite = (
        flicker        * 0.45 +
        growth         * 0.35 +
        fire_confidence * 0.20 +
        smoke_bonus
    )
    composite = float(np.clip(composite, 0.0, 1.0))

    if composite >= 0.75:
        tier = "TIER_3"
    elif composite >= 0.40:
        tier = "TIER_2"
    else:
        tier = "TIER_1"

    details = {
        "flicker":    round(flicker, 3),
        "growth":     round(growth, 3),
        "smoke_ok":   smoke_ok,
        "composite":  round(composite, 3),
        "fire_frames": fire_frames,
    }

    logger.debug("Gate1Fire cam=%s tier=%s score=%.3f %s", camera_id, tier, composite, details)
    return tier, composite, details


def reset_camera(camera_id: str) -> None:
    _pixel_histories.pop(camera_id, None)
    _bbox_areas.pop(camera_id, None)
    _fire_frame_count.pop(camera_id, None)
    _smoke_seen.pop(camera_id, None)
