"""
Aegis — ORB Feature Matching Repositioning Detector

On first call for a camera, a reference frame is saved.  Every CHECK_INTERVAL
frames the current frame is compared against the reference using ORB keypoints
+ Brute-Force matcher.

If match_ratio < MATCH_THRESHOLD the camera has been physically moved
(tilted, rotated, pointed at ceiling/wall).

Runs every CHECK_INTERVAL frames (not every frame) to save CPU.
"""
from __future__ import annotations

import cv2
import numpy as np

CHECK_INTERVAL = 30          # run ORB every N frames
MATCH_THRESHOLD = 0.25       # < 25 % of reference keypoints matched → repositioned
MIN_KEYPOINTS = 10           # skip check if reference has too few features

_orb = cv2.ORB_create(nfeatures=500)
_bf  = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

# Per-camera state
_reference_kp:   dict[str, list]       = {}
_reference_des:  dict[str, np.ndarray] = {}
_frame_counters: dict[str, int]        = {}


def check_repositioning(frame: np.ndarray, camera_id: str) -> tuple[bool, float]:
    """
    Returns (is_repositioned, match_ratio).

    match_ratio is the fraction of reference keypoints that matched in the
    current frame.  Values below MATCH_THRESHOLD indicate repositioning.
    First call always returns (False, 1.0) and saves the reference frame.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # --- First call: save reference ---
    if camera_id not in _reference_kp:
        kp, des = _orb.detectAndCompute(gray, None)
        _reference_kp[camera_id]  = kp
        _reference_des[camera_id] = des
        _frame_counters[camera_id] = 0
        return False, 1.0

    # --- Increment counter; only run every CHECK_INTERVAL frames ---
    _frame_counters[camera_id] = (_frame_counters[camera_id] + 1) % CHECK_INTERVAL
    if _frame_counters[camera_id] != 0:
        return False, 1.0

    ref_kp  = _reference_kp[camera_id]
    ref_des = _reference_des[camera_id]

    if ref_des is None or len(ref_kp) < MIN_KEYPOINTS:
        return False, 1.0

    kp, des = _orb.detectAndCompute(gray, None)
    if des is None or len(kp) < MIN_KEYPOINTS:
        # Very few features in current frame — likely obstructed not repositioned;
        # brightness_check will catch that separately.
        return False, 0.0

    matches = _bf.match(ref_des, des)
    match_ratio = len(matches) / len(ref_kp)

    is_repositioned = match_ratio < MATCH_THRESHOLD
    return is_repositioned, match_ratio


def reset_reference(camera_id: str) -> None:
    """Force a new reference frame to be captured on the next call."""
    _reference_kp.pop(camera_id, None)
    _reference_des.pop(camera_id, None)
    _frame_counters.pop(camera_id, None)
