"""
Aegis — Tamper Alert Router

Routes tamper alerts to the correct authority based on attack type:

  Physical attacks (blackout, lens_spray, repositioning)
    → on-site security guard (someone is physically at the camera)

  Digital attacks (hmac_break, feed_freeze)
    → IT / cybersecurity team (network or hardware-level compromise)

  Both simultaneously
    → everyone + CRITICAL escalation
    → crisis pipeline severity bumped to CRITICAL (coordinated attack)

Email sending is delegated to gate2_email.send_tamper_alert() which is
stubbed until Gmail credentials are provided.
"""
from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

TamperCategory = Literal["physical", "digital", "coordinated", "none"]

PHYSICAL_TYPES = {"blackout", "lens_spray", "reposition"}
DIGITAL_TYPES  = {"hmac", "feed_freeze"}


def categorise(tamper_type: str) -> TamperCategory:
    t = tamper_type.lower()
    if t in PHYSICAL_TYPES:
        return "physical"
    if t in DIGITAL_TYPES:
        return "digital"
    return "none"


class TamperRouter:
    """
    Stateful router: tracks whether physical AND digital tamper have fired
    within the same session to detect coordinated attacks.
    """

    def __init__(self) -> None:
        self._physical_fired = False
        self._digital_fired  = False

    def route(
        self,
        tamper_type: str,
        camera_id: str,
        reason: str,
        pre_tamper_frames: list | None = None,
    ) -> dict:
        """
        Process a tamper event and return a routing result dict:
          {
            "category":     "physical" | "digital" | "coordinated",
            "recipients":   ["guard"] | ["it"] | ["guard", "it", "manager"],
            "severity":     "HIGH" | "CRITICAL",
            "coordinated":  bool,
          }

        Side effect: calls gate2_email.send_tamper_alert() (stubbed).
        """
        category = categorise(tamper_type)

        if category == "physical":
            self._physical_fired = True
        elif category == "digital":
            self._digital_fired = True

        coordinated = self._physical_fired and self._digital_fired

        if coordinated:
            recipients = ["guard", "it", "manager"]
            severity   = "CRITICAL"
            cat_label  = "coordinated"
        elif category == "physical":
            recipients = ["guard"]
            severity   = "HIGH"
            cat_label  = "physical"
        elif category == "digital":
            recipients = ["it"]
            severity   = "HIGH"
            cat_label  = "digital"
        else:
            recipients = []
            severity   = "LOW"
            cat_label  = "none"

        result = {
            "category":    cat_label,
            "recipients":  recipients,
            "severity":    severity,
            "coordinated": coordinated,
        }

        logger.warning(
            "TamperRouter[%s] cam=%s type=%s severity=%s coordinated=%s reason=%s",
            cat_label, camera_id, tamper_type, severity, coordinated, reason,
        )

        # Delegate to email stub
        try:
            from gate2_email import send_tamper_alert
            send_tamper_alert(
                camera_id=camera_id,
                tamper_type=tamper_type,
                category=cat_label,
                recipients=recipients,
                severity=severity,
                reason=reason,
                pre_tamper_frames=pre_tamper_frames or [],
            )
        except Exception as exc:
            logger.warning("send_tamper_alert failed: %s", exc)

        return result

    def reset(self) -> None:
        self._physical_fired = False
        self._digital_fired  = False


# Module-level singleton shared across the pipeline
_router = TamperRouter()


def route_tamper(
    tamper_type: str,
    camera_id: str,
    reason: str,
    pre_tamper_frames: list | None = None,
) -> dict:
    return _router.route(tamper_type, camera_id, reason, pre_tamper_frames)


def reset_session() -> None:
    _router.reset()
