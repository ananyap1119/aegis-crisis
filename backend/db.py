"""
Aegis-Crisis Unified Database

Two tables:
  tamper_events  — one row per tamper detection
  crisis_events  — one row per LangGraph decision cycle

Both tables share session_id so events from the same camera run can be correlated.
DB_PATH is read from env var DB_PATH (default: data/aegis_crisis.db relative to
the project root, i.e. one directory above this file).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = str(_PROJECT_ROOT / "data" / "aegis_crisis.db")

DB_PATH = os.getenv("DB_PATH", _DEFAULT_DB_PATH)

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = _connect()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS tamper_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                camera_id   TEXT    NOT NULL,
                timestamp   REAL    NOT NULL,
                tamper_type TEXT    NOT NULL,
                reason      TEXT,
                hmac_valid  INTEGER NOT NULL DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS crisis_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT    NOT NULL,
                camera_id   TEXT    NOT NULL,
                timestamp   REAL    NOT NULL,
                frame_index INTEGER NOT NULL DEFAULT 0,
                fire        INTEGER NOT NULL DEFAULT 0,
                smoke       INTEGER NOT NULL DEFAULT 0,
                person      INTEGER NOT NULL DEFAULT 0,
                fall        INTEGER NOT NULL DEFAULT 0,
                confidence  REAL    NOT NULL DEFAULT 0.0,
                decision    TEXT,
                severity    TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("CREATE INDEX IF NOT EXISTS idx_tamper_session ON tamper_events(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tamper_camera  ON tamper_events(camera_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crisis_session ON crisis_events(session_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_crisis_camera  ON crisis_events(camera_id)")

        conn.commit()
        conn.close()


def log_tamper_event(
    *,
    session_id: str,
    camera_id: str,
    timestamp: float,
    tamper_type: str,
    reason: str,
    hmac_valid: bool,
) -> int:
    """Insert a tamper event and return its row id."""
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tamper_events
                (session_id, camera_id, timestamp, tamper_type, reason, hmac_valid)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, camera_id, timestamp, tamper_type, reason, int(hmac_valid)),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id


def log_crisis_event(
    *,
    session_id: str,
    camera_id: str,
    timestamp: float,
    frame_index: int,
    fire: bool,
    smoke: bool,
    person: bool,
    fall: bool,
    confidence: float,
    decision: str | None,
    severity: str | None,
) -> int:
    """Insert a crisis event and return its row id."""
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO crisis_events
                (session_id, camera_id, timestamp, frame_index,
                 fire, smoke, person, fall, confidence, decision, severity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                camera_id,
                timestamp,
                frame_index,
                int(fire),
                int(smoke),
                int(person),
                int(fall),
                confidence,
                decision,
                severity,
            ),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id


def get_recent_tamper_events(limit: int = 50) -> list[dict]:
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tamper_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


def get_recent_crisis_events(limit: int = 50) -> list[dict]:
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM crisis_events ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


def get_correlated_events(session_id: str) -> dict:
    """Return all tamper and crisis events for a given session."""
    with _lock:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tamper_events WHERE session_id=? ORDER BY timestamp", (session_id,))
        tampers = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT * FROM crisis_events WHERE session_id=? ORDER BY timestamp", (session_id,))
        crises = [dict(r) for r in cur.fetchall()]
        conn.close()
    return {"session_id": session_id, "tamper_events": tampers, "crisis_events": crises}
