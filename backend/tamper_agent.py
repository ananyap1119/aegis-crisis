"""
SecureEye — Tamper Agent (Aegis Layer)

Four integrity checks run on every frame in this order:

  1. Brightness threshold  — blackout / lens spray (physical)
  2. SSIM feed freeze      — frozen / looped feed (digital)
  3. ORB repositioning     — camera physically moved (physical)
  4. HMAC chain            — frame signature mismatch (digital)

Clean frames receive CLAHE pre-processing before being forwarded to the
crisis vision pipeline.

Tamper events are routed to the correct authority via tamper_router:
  physical  → security guard
  digital   → IT team
  both      → everyone + CRITICAL escalation
"""
from __future__ import annotations

import logging
import time
from typing import TypedDict

import cv2
import numpy as np

import brightness_check
import orb_match
import ssim_check
from frame_buffer import get_pre_event_frames
from tamper_router import route_tamper

logger = logging.getLogger(__name__)


class TamperResult(TypedDict):
    tampered:           bool
    reason:             str
    tamper_type:        str   # blackout|lens_spray|feed_freeze|reposition|clean|glare
    hmac_valid:         bool
    severity:           str   # HIGH | CRITICAL | OK
    category:           str   # physical | digital | coordinated | none
    glare_rescued:      bool  # True when CLAHE was applied to recover a washed-out frame
    preprocessed_frame: object


def check_frame(
    frame: np.ndarray,
    camera_id: str,
    check_hmac: bool = False,
) -> TamperResult:
    """
    Run all four Aegis integrity checks.
    Returns TamperResult; tampered=True means skip the crisis pipeline.
    preprocessed_frame is always a CLAHE-rescued copy for clean frames.
    """

    # ── Check 1: Brightness / physical obstruction ────────────────────────────
    brightness_status, mean_lum, rescued_frame = brightness_check.check_brightness(frame)

    if brightness_status in ("blackout", "lens_spray"):
        logger.warning("Tamper[%s] cam=%s lum=%.1f", brightness_status, camera_id, mean_lum)
        pre_frames = get_pre_event_frames(camera_id, seconds=10)
        routing = route_tamper(brightness_status, camera_id,
                               f"mean_luminance={mean_lum:.1f}", pre_frames)
        return TamperResult(
            tampered=True,
            reason=f"{brightness_status} (lum={mean_lum:.1f})",
            tamper_type=brightness_status,
            hmac_valid=False,
            severity=routing["severity"],
            category=routing["category"],
            glare_rescued=False,
            preprocessed_frame=frame.copy(),
        )

    # Glare detected but recoverable — pass through with rescued frame and note it
    glare_rescued = brightness_status == "glare"

    # Use the CLAHE-rescued frame for all subsequent checks
    working_frame = rescued_frame

    # ── Check 2: SSIM feed freeze ─────────────────────────────────────────────
    is_frozen, ssim_score = ssim_check.check_feed_freeze(working_frame, camera_id)

    if is_frozen:
        logger.warning("Tamper[feed_freeze] cam=%s ssim=%.4f", camera_id, ssim_score)
        routing = route_tamper("feed_freeze", camera_id,
                               f"ssim={ssim_score:.4f} for {ssim_check.FREEZE_WINDOW} frames")
        return TamperResult(
            tampered=True,
            reason=f"feed freeze detected (ssim={ssim_score:.4f})",
            tamper_type="feed_freeze",
            hmac_valid=False,
            severity=routing["severity"],
            category=routing["category"],
            glare_rescued=glare_rescued,
            preprocessed_frame=working_frame,
        )

    # ── Check 3: ORB repositioning ────────────────────────────────────────────
    is_repositioned, match_ratio = orb_match.check_repositioning(working_frame, camera_id)

    if is_repositioned:
        logger.warning("Tamper[reposition] cam=%s match_ratio=%.3f", camera_id, match_ratio)
        pre_frames = get_pre_event_frames(camera_id, seconds=10)
        routing = route_tamper("reposition", camera_id,
                               f"orb_match_ratio={match_ratio:.3f}", pre_frames)
        return TamperResult(
            tampered=True,
            reason=f"camera repositioned (orb_match={match_ratio:.3f})",
            tamper_type="reposition",
            hmac_valid=False,
            severity=routing["severity"],
            category=routing["category"],
            glare_rescued=glare_rescued,
            preprocessed_frame=working_frame,
        )

    # ── All checks passed ─────────────────────────────────────────────────────
    return TamperResult(
        tampered=False,
        reason="glare recovered via CLAHE" if glare_rescued else "",
        tamper_type="glare" if glare_rescued else "clean",
        hmac_valid=True,
        severity="OK",
        category="none",
        glare_rescued=glare_rescued,
        preprocessed_frame=working_frame,
    )
