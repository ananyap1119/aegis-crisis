"""Tests ported from ai-crisis-response/tests/test_fusion_logic.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main_unified import build_fusion_fallback


def test_fusion_prefers_high_confidence_for_multi_signal_fire() -> None:
    state = {
        "camera_id": "cam-1",
        "crisis": "SAFE",
        "vision_event": {
            "validation_state": "MONITOR",
            "validation_reason": "no smoke support; temporal 1/2",
            "raw_fire_detected": True,
            "raw_smoke_detected": False,
            "confidence": 0.42,
        },
        "social": {
            "type": "FIRE",
            "confidence": 0.75,
            "source": "social",
            "text": "Fire reported in mall",
            "location": "mall",
        },
    }

    result = build_fusion_fallback(state)

    assert result["is_crisis"] is True
    assert result["crisis_type"] == "FIRE"
    assert result["confidence"] == "HIGH"
