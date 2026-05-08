"""Tests ported from ai-crisis-response/tests/test_decision_engine.py"""
from decision_engine import decision_engine, detect_danger


def test_detect_danger_returns_both_when_fire_and_fall_exist() -> None:
    event = {
        "fire": True,
        "smoke": False,
        "fall_detected": True,
    }
    assert detect_danger(event) == "BOTH"


def test_decision_mapping() -> None:
    assert decision_engine("FIRE") == "ALERT_FIRE_STATION"
    assert decision_engine("MEDICAL") == "ALERT_AMBULANCE"
    assert decision_engine("BOTH") == "ALERT_BOTH"
    assert decision_engine("SAFE") == "NO_ACTION"
