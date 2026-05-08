from __future__ import annotations

from pipeline_support import VisionEvent


def detect_danger(event: VisionEvent | dict) -> str:
    fire_risk = event["fire"] or event["smoke"]
    medical_risk = event["fall_detected"]

    if fire_risk and medical_risk:
        return "BOTH"
    if fire_risk:
        return "FIRE"
    if medical_risk:
        return "MEDICAL"
    return "SAFE"


def decision_engine(danger: str) -> str:
    if danger == "FIRE":
        return "ALERT_FIRE_STATION"
    if danger == "MEDICAL":
        return "ALERT_AMBULANCE"
    if danger == "BOTH":
        return "ALERT_BOTH"
    return "NO_ACTION"
