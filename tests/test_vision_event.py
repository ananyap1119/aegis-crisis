"""Tests ported from ai-crisis-response/tests/test_vision_event.py"""
import numpy as np
import vision_agent


def test_process_frame_returns_normalized_event(monkeypatch) -> None:
    def fake_detect_person_and_fall(frame, event):
        event["person"] = True
        event["fall_detected"] = True
        return 0.72, [(1, 1, 10, 4)]

    def fake_detect_fire_and_smoke(frame, event, camera_id):
        event["smoke"] = True
        event["smoke_confidence"] = 0.61
        event["raw_smoke_detected"] = True
        return 0.61

    monkeypatch.setattr(vision_agent, "detect_person_and_fall", fake_detect_person_and_fall)
    monkeypatch.setattr(vision_agent, "detect_fire_and_smoke", fake_detect_fire_and_smoke)

    frame = np.zeros((24, 24, 3), dtype=np.uint8)
    event = vision_agent.process_frame(frame, camera_id="cam-2", frame_index=8)

    assert event["camera_id"] == "cam-2"
    assert event["frame_index"] == 8
    assert event["smoke"] is True
    assert event["person"] is True
    assert event["fall_detected"] is True
    assert event["confidence"] == 0.72
    assert event["smoke_confidence"] == 0.61
    assert event["fire"] is False
    assert event["raw_fire_detected"] is False
    assert event["raw_smoke_detected"] is True
    # New fields added in aegis-crisis — tamper defaults
    assert "tamper_status" in event
    assert event["tamper_status"] is False
    assert "tamper_reason" in event


def test_event_to_crisis_prefers_combined_state() -> None:
    event = {
        "fire": True,
        "smoke": False,
        "fall_detected": True,
    }
    assert vision_agent.event_to_crisis(event) == "BOTH"
