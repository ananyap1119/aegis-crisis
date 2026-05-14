"""
Aegis-Crisis — Circular Frame Buffer

Maintains a rolling 10-second deque of raw frames per camera.
Used by clip_writer.py to extract pre-event footage for Gate 2 review emails.

Usage:
    from frame_buffer import FrameBuffer
    buf = FrameBuffer()
    buf.push("cam-1", frame, fps=30)
    pre_event_frames = buf.get_last_n_seconds("cam-1", seconds=5)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

BUFFER_SECONDS = 10
DEFAULT_FPS    = 30


@dataclass
class FrameBuffer:
    fps: int = DEFAULT_FPS
    _buffers: dict[str, deque] = field(default_factory=dict)

    def _get_buf(self, camera_id: str) -> deque:
        if camera_id not in self._buffers:
            maxlen = self.fps * BUFFER_SECONDS
            self._buffers[camera_id] = deque(maxlen=maxlen)
        return self._buffers[camera_id]

    def push(self, camera_id: str, frame: np.ndarray, fps: int | None = None) -> None:
        if fps and fps != self.fps:
            # Resize buffer if fps changed
            old = list(self._buffers.get(camera_id, []))
            self.fps = fps
            buf = deque(old, maxlen=fps * BUFFER_SECONDS)
            self._buffers[camera_id] = buf
        self._get_buf(camera_id).append(frame.copy())

    def get_last_n_seconds(self, camera_id: str, seconds: int = 5) -> list[np.ndarray]:
        buf = self._get_buf(camera_id)
        n = min(len(buf), self.fps * seconds)
        return list(buf)[-n:]

    def get_all(self, camera_id: str) -> list[np.ndarray]:
        return list(self._get_buf(camera_id))

    def clear(self, camera_id: str) -> None:
        self._get_buf(camera_id).clear()


# Module-level singleton shared across the pipeline
_global_buffer = FrameBuffer()


def push_frame(camera_id: str, frame: np.ndarray, fps: int = DEFAULT_FPS) -> None:
    _global_buffer.push(camera_id, frame, fps)


def get_pre_event_frames(camera_id: str, seconds: int = 10) -> list[np.ndarray]:
    return _global_buffer.get_last_n_seconds(camera_id, seconds)
