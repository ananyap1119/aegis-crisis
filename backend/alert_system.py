from __future__ import annotations

import logging

from pipeline_support import log_payload


logger = logging.getLogger(__name__)

ALERT_MESSAGES = {
    "ALERT_FIRE_STATION": "Fire station alert sent",
    "ALERT_AMBULANCE": "Ambulance alert sent",
    "ALERT_BOTH": "Fire station + ambulance alert sent",
}


def send_alert(action: str, camera_id: str = "camera-0", details: str | None = None) -> None:
    message = ALERT_MESSAGES.get(action)
    payload = {
        "camera_id": camera_id,
        "action": action,
        "details": details or "",
    }

    if message is None:
        payload["message"] = "No external alert dispatched"
        log_payload(logger, logging.INFO, "alert_skipped", payload)
        return

    payload["message"] = message
    log_payload(logger, logging.WARNING, "alert_dispatched", payload)
