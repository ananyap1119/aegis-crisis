"""
Aegis-Crisis Tamper Agent

Wraps Aegis tamper detection pipeline:
  blur detection → shake detection → reposition detection → HMAC verification
  → CLAHE glare rescue (pre-processing for clean frames)

Returns a TamperResult dict that main_unified.py uses to decide whether to pass
the frame forward to the crisis vision pipeline.
"""
from __future__ import annotations

import logging
import time
from typing import TypedDict

import cv2
import numpy as np

from tamper_detector import (
    check_blur,
    check_shake,
    detect_camera_reposition,
    fix_blur_unsharp_mask,
)
from watermark_embedder import get_hmac_color
from watermark_extractor import extract_watermark_color

logger = logging.getLogger(__name__)

BLUR_THRESHOLD = 25.0
SHAKE_THRESHOLD = 5.0
REPOSITION_THRESHOLD = 7.0
HMAC_MATCH_TOLERANCE_SECONDS = 2

# Per-camera state for optical flow (prev_gray)
_prev_gray_store: dict[str, np.ndarray | None] = {}

# CLAHE instance (shared, thread-safe for reading)
_clahe = cv2.createCLAHE(clipLimit=16.0, tileGridSize=(4, 4))


class TamperResult(TypedDict):
    tampered: bool
    reason: str
    tamper_type: str          # blur | shake | reposition | hmac | clean
    hmac_valid: bool
    preprocessed_frame: object  # ndarray — CLAHE-rescued if glare, else original


def _verify_hmac(frame: np.ndarray) -> bool:
    """Extract watermark color from frame and compare to expected HMAC color for now."""
    extracted = extract_watermark_color(frame)
    if extracted is None:
        return False
    expected = get_hmac_color(int(time.time()))
    # Allow ±HMAC_MATCH_TOLERANCE_SECONDS window
    for delta in range(-HMAC_MATCH_TOLERANCE_SECONDS, HMAC_MATCH_TOLERANCE_SECONDS + 1):
        candidate = get_hmac_color(int(time.time()) + delta)
        dist = np.sqrt(sum((a - b) ** 2 for a, b in zip(extracted, candidate)))
        if dist < 30:
            return True
    return False


def _apply_clahe(frame: np.ndarray) -> np.ndarray:
    """Apply CLAHE + unsharp mask + highlight taming as Aegis does."""
    try:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        l_clahe = _clahe.apply(l)
        enhanced_lab = cv2.merge((l_clahe, a, b))
        rescued = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

        # Unsharp mask sharpening
        blurred = cv2.GaussianBlur(rescued, (5, 5), 1.0)
        rescued = cv2.addWeighted(rescued, 2.0, blurred, -1.0, 0)

        # Tame blown-out highlights
        gray_raw = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_raw, 252, 255, cv2.THRESH_BINARY)
        rescued[mask > 0] = (150, 150, 150)

        return rescued
    except Exception as exc:
        logger.warning("CLAHE rescue failed: %s", exc)
        return frame.copy()


def check_frame(
    frame: np.ndarray,
    camera_id: str,
    check_hmac: bool = True,
) -> TamperResult:
    """
    Run the full tamper detection pipeline on a single frame.

    Returns a TamperResult.  If tampered=True the caller should skip the
    frame from crisis detection.  preprocessed_frame is always set to a
    glare-rescued copy even when the frame is clean.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prev_gray = _prev_gray_store.get(camera_id)
    _prev_gray_store[camera_id] = gray

    # --- Blur ---
    is_blurred, blur_var = check_blur(gray, threshold=BLUR_THRESHOLD)
    if is_blurred:
        logger.info("Tamper[blur] cam=%s variance=%.2f", camera_id, blur_var)
        return TamperResult(
            tampered=True,
            reason=f"blur detected (variance={blur_var:.2f})",
            tamper_type="blur",
            hmac_valid=False,
            preprocessed_frame=frame.copy(),
        )

    # --- Shake ---
    if prev_gray is not None:
        is_shaken, shake_mag = check_shake(gray, prev_gray, threshold=SHAKE_THRESHOLD)
        if is_shaken:
            logger.info("Tamper[shake] cam=%s magnitude=%.2f", camera_id, shake_mag)
            return TamperResult(
                tampered=True,
                reason=f"shake detected (magnitude={shake_mag:.2f})",
                tamper_type="shake",
                hmac_valid=False,
                preprocessed_frame=frame.copy(),
            )

        # --- Reposition ---
        is_repositioned, shift_mag, _, _ = detect_camera_reposition(
            gray, prev_gray, threshold_shift=REPOSITION_THRESHOLD
        )
        if is_repositioned:
            logger.info("Tamper[reposition] cam=%s shift=%.2f", camera_id, shift_mag)
            return TamperResult(
                tampered=True,
                reason=f"camera repositioned (shift={shift_mag:.2f})",
                tamper_type="reposition",
                hmac_valid=False,
                preprocessed_frame=frame.copy(),
            )

    # --- HMAC watermark verification ---
    hmac_valid = True
    if check_hmac:
        hmac_valid = _verify_hmac(frame)
        if not hmac_valid:
            logger.info("Tamper[hmac] cam=%s — watermark mismatch", camera_id)
            return TamperResult(
                tampered=True,
                reason="HMAC watermark verification failed",
                tamper_type="hmac",
                hmac_valid=False,
                preprocessed_frame=frame.copy(),
            )

    # --- Clean: apply CLAHE glare rescue as pre-processing ---
    preprocessed = _apply_clahe(frame)

    return TamperResult(
        tampered=False,
        reason="",
        tamper_type="clean",
        hmac_valid=hmac_valid,
        preprocessed_frame=preprocessed,
    )
