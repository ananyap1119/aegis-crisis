"""
SecureEye — Gate 2 Email Alerts

Rules:
  - Maximum 1 email per camera per alert type every 3 minutes (COOLDOWN_SECONDS)
  - Every email contains a "Stop Alerts" button that hits /api/stop_alerts
  - Once stopped, alerts for that camera+type stay silent for the session
    (restart backend to reset)

Recipients:
  fire_review   → GMAIL_MANAGER
  fall_review   → GMAIL_GUARD + GMAIL_MANAGER
  tamper_alert  → GMAIL_GUARD (physical) | GMAIL_IT (digital) | all (coordinated)
  tier3_fire    → GMAIL_MANAGER + GMAIL_IT (auto-dispatch, no human review)
"""
from __future__ import annotations

import logging
import os
import smtplib
import time
import uuid
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 180   # 3 minutes between repeated alerts
BASE_URL         = os.getenv("SECUREEYE_API_URL", "http://localhost:5000")
SENDER           = os.getenv("GMAIL_SENDER", "")
APP_PASSWORD     = os.getenv("GMAIL_APP_PASSWORD", "")

RECIPIENT_MAP = {
    "guard":   os.getenv("GMAIL_GUARD",   ""),
    "it":      os.getenv("GMAIL_IT",      ""),
    "manager": os.getenv("GMAIL_MANAGER", ""),
}

# ── Cooldown + stop state ─────────────────────────────────────────────────────
_lock:       Lock         = Lock()
_last_sent:  dict[str, float] = {}   # key → last send timestamp
_stopped:    set[str]         = set() # keys that have been stopped by user


def _key(camera_id: str, alert_type: str) -> str:
    return f"{camera_id}:{alert_type}"


def _can_send(camera_id: str, alert_type: str) -> bool:
    k = _key(camera_id, alert_type)
    with _lock:
        if k in _stopped:
            logger.info("Email suppressed (stopped by user): %s", k)
            return False
        last = _last_sent.get(k, 0.0)
        if time.time() - last < COOLDOWN_SECONDS:
            logger.debug("Email suppressed (cooldown): %s", k)
            return False
        _last_sent[k] = time.time()
        return True


def stop_alerts(camera_id: str, alert_type: str) -> None:
    k = _key(camera_id, alert_type)
    with _lock:
        _stopped.add(k)
    logger.info("Alerts stopped for camera=%s type=%s", camera_id, alert_type)


def resume_alerts(camera_id: str, alert_type: str) -> None:
    k = _key(camera_id, alert_type)
    with _lock:
        _stopped.discard(k)
        _last_sent.pop(k, None)


# ── SMTP helper ───────────────────────────────────────────────────────────────

def _send(to_addrs: list[str], subject: str, body_html: str, attachment: str | None = None) -> bool:
    if not SENDER or not APP_PASSWORD:
        logger.warning("Gmail not configured — email stub. Subject: %s → %s", subject, to_addrs)
        return False

    to_addrs = [a for a in to_addrs if a]
    if not to_addrs:
        logger.warning("No recipients configured for: %s", subject)
        return False

    msg            = MIMEMultipart()
    msg["From"]    = SENDER
    msg["To"]      = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg.attach(MIMEText(body_html, "html"))

    if attachment and Path(attachment).exists():
        with open(attachment, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f'attachment; filename="{Path(attachment).name}"')
        msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER, APP_PASSWORD)
            server.sendmail(SENDER, to_addrs, msg.as_string())
        logger.info("Email sent '%s' → %s", subject, to_addrs)
        return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


def _stop_button(camera_id: str, alert_type: str) -> str:
    url = f"{BASE_URL}/api/stop_alerts?camera_id={camera_id}&type={alert_type}"
    return (
        f'<a href="{url}" style="background:#555;color:white;padding:8px 16px;'
        f'text-decoration:none;border-radius:4px;font-size:12px;">Stop These Alerts</a>'
    )


def _confirm_url(event_id: str, action: str) -> str:
    return f"{BASE_URL}/api/review?event_id={event_id}&action={action}"


# ── Fire Tier 2 review ────────────────────────────────────────────────────────

def send_fire_review(
    camera_id: str,
    clip_path: str | None,
    confidence: float,
    location: str = "unknown",
) -> str | None:
    if not _can_send(camera_id, "fire_review"):
        return None

    event_id        = str(uuid.uuid4())[:8]
    confirm_url     = _confirm_url(event_id, "confirm_fire")
    onsite_url      = _confirm_url(event_id, "onsite_handles")
    false_alarm_url = _confirm_url(event_id, "false_alarm")

    subject = f"[SecureEye] 🔥 Fire Review Required — {location} ({camera_id})"
    body = f"""
    <h2>🔥 Fire Detected — Human Review Required</h2>
    <p><b>Camera:</b> {camera_id}<br>
       <b>Location:</b> {location}<br>
       <b>Confidence:</b> {confidence:.0%}</p>
    <p>Please review the attached clip and respond:</p>
    <p>
      <a href="{confirm_url}" style="background:#d32f2f;color:white;padding:10px 20px;text-decoration:none;border-radius:4px;margin-right:8px;">
        Confirm → Dispatch Fire Dept
      </a>
      <a href="{onsite_url}" style="background:#f57c00;color:white;padding:10px 20px;text-decoration:none;border-radius:4px;margin-right:8px;">
        On-site Team Handles
      </a>
      <a href="{false_alarm_url}" style="background:#388e3c;color:white;padding:10px 20px;text-decoration:none;border-radius:4px;">
        False Alarm
      </a>
    </p>
    <hr style="margin:20px 0">
    <p>{_stop_button(camera_id, "fire_review")}</p>
    <p><small>Event ID: {event_id} · Next alert in 3 minutes if not stopped.</small></p>
    """
    _send([RECIPIENT_MAP["manager"]], subject, body, clip_path)
    return event_id


# ── Fire Tier 3 auto-dispatch ─────────────────────────────────────────────────

def send_tier3_fire(
    camera_id: str,
    confidence: float,
    location: str = "unknown",
) -> None:
    if not _can_send(camera_id, "tier3_fire"):
        return

    subject = f"[SecureEye] 🚨 AUTO-DISPATCH — Tier 3 Fire — {location} ({camera_id})"
    body = f"""
    <h2>🚨 Tier 3 Fire — Automatic Dispatch</h2>
    <p>This fire has been confirmed as fast-growing. No human review required.</p>
    <p><b>Camera:</b> {camera_id}<br>
       <b>Location:</b> {location}<br>
       <b>Confidence:</b> {confidence:.0%}<br>
       <b>Action:</b> Fire department notified automatically.</p>
    <hr style="margin:20px 0">
    <p>{_stop_button(camera_id, "tier3_fire")}</p>
    <p><small>Next alert in 3 minutes if not stopped.</small></p>
    """
    _send([RECIPIENT_MAP["manager"], RECIPIENT_MAP["it"]], subject, body)


# ── Fall escalation review ────────────────────────────────────────────────────

def send_fall_review(
    camera_id: str,
    clip_path: str | None,
    elapsed_s: float,
    location: str = "unknown",
) -> str | None:
    if not _can_send(camera_id, "fall_review"):
        return None

    event_id    = str(uuid.uuid4())[:8]
    confirm_url = _confirm_url(event_id, "confirm_fall")
    false_url   = _confirm_url(event_id, "false_alarm")

    subject = f"[SecureEye] 🚑 Fall Review Required — {location} ({camera_id})"
    body = f"""
    <h2>🚑 Person Fall Detected — Human Review Required</h2>
    <p><b>Camera:</b> {camera_id}<br>
       <b>Location:</b> {location}<br>
       <b>Time on ground:</b> {elapsed_s:.1f} seconds — person has not recovered.</p>
    <p>
      <a href="{confirm_url}" style="background:#d32f2f;color:white;padding:10px 20px;text-decoration:none;border-radius:4px;margin-right:8px;">
        Confirm Emergency
      </a>
      <a href="{false_url}" style="background:#388e3c;color:white;padding:10px 20px;text-decoration:none;border-radius:4px;">
        False Alarm
      </a>
    </p>
    <hr style="margin:20px 0">
    <p>{_stop_button(camera_id, "fall_review")}</p>
    <p><small>Event ID: {event_id} · Next alert in 3 minutes if not stopped.</small></p>
    """
    _send([RECIPIENT_MAP["guard"], RECIPIENT_MAP["manager"]], subject, body, clip_path)
    return event_id


# ── Tamper alert ──────────────────────────────────────────────────────────────

def send_tamper_alert(
    camera_id: str,
    tamper_type: str,
    category: str,
    recipients: list[str],
    severity: str,
    reason: str,
    pre_tamper_frames: list | None = None,
) -> None:
    alert_type = f"tamper_{category}"
    if not _can_send(camera_id, alert_type):
        return

    from clip_writer import make_tamper_clip
    clip_path = None
    if pre_tamper_frames:
        try:
            clip_path = make_tamper_clip(pre_tamper_frames, camera_id)
        except Exception as exc:
            logger.warning("Tamper clip write failed: %s", exc)

    to_addrs = [RECIPIENT_MAP.get(r, "") for r in recipients]
    emoji    = "🔴" if severity == "CRITICAL" else "⚠️"
    subject  = f"[SecureEye {severity}] {emoji} Camera Tamper — {tamper_type} on {camera_id}"
    body = f"""
    <h2>{emoji} Camera Tamper Detected</h2>
    <p><b>Camera:</b> {camera_id}<br>
       <b>Type:</b> {tamper_type}<br>
       <b>Category:</b> {category}<br>
       <b>Severity:</b> {severity}<br>
       <b>Reason:</b> {reason}</p>
    {"<p><b>⚠️ COORDINATED ATTACK — physical + digital tamper fired simultaneously. Crisis pipeline escalated to CRITICAL.</b></p>" if severity == "CRITICAL" else ""}
    <hr style="margin:20px 0">
    <p>{_stop_button(camera_id, alert_type)}</p>
    <p><small>Next alert in 3 minutes if not stopped.</small></p>
    """
    _send(to_addrs, subject, body, clip_path)
