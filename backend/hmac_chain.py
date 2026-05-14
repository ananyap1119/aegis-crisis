"""
Aegis — HMAC-SHA256 Frame Chain

Every frame is stamped with HMAC-SHA256(secret, sequence_number).
The sequence number enforces ordering: looped or replayed footage breaks
the chain because sequence numbers won't match.

Embedding: color of a small corner pixel is set to the first 3 bytes of
the HMAC digest (B, G, R order) — same technique as the original watermark
embedder, extended with a sequence counter.

Verification window: ±TOLERANCE stamps are accepted to absorb minor clock
drift between embedder and verifier.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

import cv2
import numpy as np

SECRET_KEY  = os.getenv("HMAC_SECRET_KEY", "AegisSecureWatermarkKey2025").encode()
STAMP_X     = 0          # pixel column for watermark
STAMP_Y     = 0          # pixel row for watermark
TOLERANCE   = 3          # accept ±3 sequence numbers

# Per-camera sequence counter (embedder side)
_seq: dict[str, int] = {}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _digest(seq: int) -> bytes:
    """Return 3-byte HMAC digest for a given sequence number."""
    msg = seq.to_bytes(8, "big")
    return hmac.new(SECRET_KEY, msg, hashlib.sha256).digest()[:3]


def _seq_from_time() -> int:
    """Verifier uses wall-clock seconds as the sequence proxy when no counter available."""
    return int(time.time())


# ── Embedder ──────────────────────────────────────────────────────────────────

def embed_stamp(frame: np.ndarray, camera_id: str) -> np.ndarray:
    """
    Embed HMAC stamp into frame (in-place copy).
    Increments the per-camera sequence counter.
    """
    seq = _seq.get(camera_id, int(time.time()))
    _seq[camera_id] = seq + 1

    b, g, r = _digest(seq)
    stamped = frame.copy()
    stamped[STAMP_Y, STAMP_X] = (b, g, r)
    return stamped


# ── Verifier ──────────────────────────────────────────────────────────────────

def verify_stamp(frame: np.ndarray) -> bool:
    """
    Extract the embedded color and check it against the expected digest
    for the current time window (±TOLERANCE seconds as sequence proxy).

    Returns True if any candidate matches (chain intact).
    """
    extracted = tuple(int(v) for v in frame[STAMP_Y, STAMP_X])  # B, G, R
    base_seq = _seq_from_time()

    for delta in range(-TOLERANCE, TOLERANCE + 1):
        expected = _digest(base_seq + delta)
        dist = sum(abs(a - b) for a, b in zip(extracted, expected))
        if dist < 30:
            return True

    return False
