"""
Aegis — SSIM Feed Freeze Detector

Real cameras always score ~0.92–0.96 between consecutive frames due to sensor
noise, compression variance, and micro lighting shifts.  A frozen or looped
feed scores 0.99–1.00.

Detection rule: SSIM > 0.98 for FREEZE_WINDOW consecutive frames → FEED_FREEZE.

Catches: source-level feed freeze, raw pixel repetition over the network.
SHA-256 cannot catch this because a frozen frame at camera source still gets
a fresh valid HMAC stamp each second.
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np

try:
    from skimage.metrics import structural_similarity as ssim
except ImportError:
    ssim = None  # graceful degradation — check is skipped

SSIM_FREEZE_THRESHOLD = 0.98   # above this = suspiciously static
FREEZE_WINDOW = 90             # 3 seconds at 30 fps

# Per-camera SSIM history
_ssim_history: dict[str, deque[float]] = {}
_prev_gray: dict[str, np.ndarray] = {}


def check_feed_freeze(frame: np.ndarray, camera_id: str) -> tuple[bool, float]:
    """
    Returns (is_frozen, ssim_score).
    is_frozen=True means the feed has been static for >= FREEZE_WINDOW frames.
    ssim_score is the similarity to the previous frame (0–1).
    """
    if ssim is None:
        return False, 0.0

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    history = _ssim_history.setdefault(camera_id, deque(maxlen=FREEZE_WINDOW))
    prev = _prev_gray.get(camera_id)
    _prev_gray[camera_id] = gray

    if prev is None:
        return False, 0.0

    # Resize if shapes differ (shouldn't happen but be safe)
    if prev.shape != gray.shape:
        prev = cv2.resize(prev, (gray.shape[1], gray.shape[0]))

    score = float(ssim(prev, gray, data_range=255))
    history.append(score)

    if len(history) < FREEZE_WINDOW:
        return False, score

    is_frozen = all(s > SSIM_FREEZE_THRESHOLD for s in history)
    return is_frozen, score


def reset_camera(camera_id: str) -> None:
    _ssim_history.pop(camera_id, None)
    _prev_gray.pop(camera_id, None)
