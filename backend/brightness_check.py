"""
Aegis — Brightness Threshold Detector

Detects physical camera obstruction via mean luminance:

  mean < BLACKOUT_THRESHOLD  → BLACKOUT  (hand, tape, jacket over lens)
  CLAHE recovery still dark  → LENS_SPRAY (spray paint, persistent obstruction)

CLAHE is attempted first so legitimate low-light scenes are rescued before
being flagged.  Only if enhancement fails to bring the frame above the
recovery threshold is it classified as LENS_SPRAY.
"""
from __future__ import annotations

import cv2
import numpy as np

BLACKOUT_THRESHOLD = 15.0        # mean luminance 0-255; below = blackout
RECOVERY_THRESHOLD = 25.0        # post-CLAHE mean; still below = lens spray
GLARE_THRESHOLD_PCT = 10.0       # % of pixels >= 250 that triggers glare flag

_clahe = cv2.createCLAHE(clipLimit=16.0, tileGridSize=(4, 4))


def check_brightness(frame: np.ndarray) -> tuple[str, float, np.ndarray]:
    """
    Returns (status, mean_luminance, rescued_frame).

    status is one of:
      'ok'          — frame is usable as-is
      'blackout'    — mean < BLACKOUT_THRESHOLD, CLAHE rescued it
      'lens_spray'  — mean < BLACKOUT_THRESHOLD and CLAHE failed
      'glare'       — too many blown-out pixels; CLAHE applied
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_lum = float(gray.mean())

    # --- Physical obstruction ---
    if mean_lum < BLACKOUT_THRESHOLD:
        rescued = _apply_clahe(frame)
        rescued_gray = cv2.cvtColor(rescued, cv2.COLOR_BGR2GRAY)
        if float(rescued_gray.mean()) < RECOVERY_THRESHOLD:
            return "lens_spray", mean_lum, frame.copy()
        return "blackout", mean_lum, rescued

    # --- Glare ---
    total = gray.shape[0] * gray.shape[1]
    white_pct = float(np.sum(gray >= 250)) / total * 100
    if white_pct > GLARE_THRESHOLD_PCT:
        return "glare", mean_lum, _apply_clahe(frame)

    return "ok", mean_lum, frame.copy()


def _apply_clahe(frame: np.ndarray) -> np.ndarray:
    try:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_clahe = _clahe.apply(l)
        enhanced = cv2.merge((l_clahe, a, b))
        rescued = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        blurred = cv2.GaussianBlur(rescued, (5, 5), 1.0)
        rescued = cv2.addWeighted(rescued, 2.0, blurred, -1.0, 0)

        gray_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_raw, 252, 255, cv2.THRESH_BINARY)
        rescued[mask > 0] = (150, 150, 150)

        return rescued
    except Exception:
        return frame.copy()
