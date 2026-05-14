"""
SecureEye — Twilio SMS Dispatch (Stub)

Tier 3 fires (fast-growing, multi-camera confirmed) bypass human Gate 2 review
and dispatch directly via SMS to the fire department.

To activate: set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO
in .env and replace the stub body below with the real Twilio SDK call.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def send_sms_alert(
    camera_id: str,
    event_type: str,
    severity: str,
    location: str,
    details: str = "",
) -> bool:
    """
    Send an SMS alert for Tier 3 fire dispatch.

    Returns True if sent successfully, False otherwise.
    Currently stubbed — logs the message that would be sent.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_FROM", "")
    to_number   = os.getenv("TWILIO_TO", "")

    message = (
        f"[SecureEye TIER-3 ALERT] {event_type} confirmed at {location} "
        f"(camera={camera_id}, severity={severity}). {details} "
        f"Auto-dispatching — no human review required."
    )

    if not all([account_sid, auth_token, from_number, to_number]):
        logger.warning(
            "Twilio not configured — SMS stub fired. Message: %s", message
        )
        return False

    # ── Activate when credentials are provided ────────────────────────────────
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # client.messages.create(body=message, from_=from_number, to=to_number)
    # logger.info("Twilio SMS sent to %s", to_number)
    # return True
    # ─────────────────────────────────────────────────────────────────────────

    logger.info("Twilio stub — would have sent: %s", message)
    return False
