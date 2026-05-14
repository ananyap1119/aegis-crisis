"""
SecureEye — Clip Writer

Extracts a video clip from the circular frame buffer and writes it to disk.
Used by gate2_email.py to attach evidence clips to review emails.

Fire clip:  5 s pre-event + 15 s post-event
Fall clip:  2 s pre-event +  8 s post-event
Tamper clip: last 10 s of pre-tamper footage
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

CLIP_DIR = Path(os.getenv("DEBUG_FRAME_DIR", "debug_fire_frames")) / "clips"
FPS      = 30


def write_clip(
    frames: list[np.ndarray],
    label: str = "clip",
    fps: int = FPS,
) -> str | None:
    """
    Write a list of frames to an MP4 file.

    Returns the file path on success, None on failure.
    """
    if not frames:
        return None

    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    path = CLIP_DIR / f"{label}_{timestamp}.mp4"

    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))

    if not writer.isOpened():
        logger.error("clip_writer: could not open VideoWriter for %s", path)
        return None

    for frame in frames:
        if frame.shape[:2] != (h, w):
            frame = cv2.resize(frame, (w, h))
        writer.write(frame)

    writer.release()
    logger.info("clip_writer: wrote %d frames → %s", len(frames), path)
    return str(path)


def make_fire_clip(
    pre_frames: list[np.ndarray],
    post_frames: list[np.ndarray],
    camera_id: str,
) -> str | None:
    pre  = pre_frames[-FPS * 5:]   # last 5 s
    post = post_frames[: FPS * 15] # first 15 s
    return write_clip(pre + post, label=f"fire_{camera_id}")


def make_fall_clip(
    pre_frames: list[np.ndarray],
    post_frames: list[np.ndarray],
    camera_id: str,
) -> str | None:
    pre  = pre_frames[-FPS * 2:]  # last 2 s
    post = post_frames[: FPS * 8] # first 8 s
    return write_clip(pre + post, label=f"fall_{camera_id}")


def make_tamper_clip(
    pre_frames: list[np.ndarray],
    camera_id: str,
) -> str | None:
    return write_clip(pre_frames[-FPS * 10:], label=f"tamper_{camera_id}")
