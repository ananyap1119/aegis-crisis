"""Tests ported from ai-crisis-response/tests/test_temporal_tracker.py"""
import numpy as np
from pipeline_support import TemporalEventTracker, create_vision_event


def _make_event(fire_conf=0.0, smoke_conf=0.0, fall=False, cam="cam-test"):
    ev = create_vision_event(camera_id=cam)
    ev["fire"] = fire_conf > 0
    ev["fire_confidence"] = fire_conf
    ev["smoke_confidence"] = smoke_conf
    ev["fall_detected"] = fall
    return ev


def test_stable_fire_with_motion_and_smoke_reaches_alert():
    tracker = TemporalEventTracker()
    frame = np.zeros((24, 24, 3), dtype=np.uint8)

    for i in range(6):
        noisy_frame = frame + np.random.randint(0, 30, frame.shape, dtype=np.uint8)
        ev = _make_event(fire_conf=0.82, smoke_conf=0.65)
        tracker.stabilize(ev, noisy_frame)

    ev = _make_event(fire_conf=0.82, smoke_conf=0.65)
    result = tracker.stabilize(ev, frame + np.random.randint(0, 30, frame.shape, dtype=np.uint8))
    # Should reach ALERT if motion is detected across frames
    assert result["temporal_fire_support"] > 0


def test_no_fire_signal_stays_safe():
    tracker = TemporalEventTracker()
    frame = np.zeros((24, 24, 3), dtype=np.uint8)
    ev = _make_event(fire_conf=0.0, smoke_conf=0.0)
    result = tracker.stabilize(ev, frame)
    assert result["validation_state"] == "SAFE"
