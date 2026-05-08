"""Tests ported from ai-crisis-response/tests/test_social_agent.py"""
from social_agent import fetch_social_signals, simulate_social_signals


def test_fetch_fire_signal_from_query() -> None:
    result = fetch_social_signals("fire smoke emergency", location="mall")
    assert result["type"] == "FIRE"
    assert result["confidence"] > 0


def test_fetch_returns_safe_for_no_signal() -> None:
    result = fetch_social_signals("all clear nothing to see here", location="nowhere")
    assert result["type"] == "SAFE"


def test_simulate_fire_signals() -> None:
    sigs = simulate_social_signals("fire")
    assert len(sigs) > 0
    assert all("confidence" in s for s in sigs)


def test_simulate_fall_signals() -> None:
    sigs = simulate_social_signals("fall")
    assert len(sigs) > 0
