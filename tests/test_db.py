"""Tests for the unified database module."""
import os
import time
import tempfile
import pytest

import db


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point DB_PATH to a temp file for each test."""
    db_file = str(tmp_path / "test_aegis_crisis.db")
    monkeypatch.setattr(db, "DB_PATH", db_file)
    db.init_db()
    yield
    if os.path.exists(db_file):
        os.remove(db_file)


def test_log_tamper_event_roundtrip():
    row_id = db.log_tamper_event(
        session_id="sess-1",
        camera_id="cam-a",
        timestamp=time.time(),
        tamper_type="blur",
        reason="variance=12.3",
        hmac_valid=False,
    )
    assert row_id is not None and row_id > 0

    events = db.get_recent_tamper_events(limit=10)
    assert len(events) == 1
    assert events[0]["camera_id"] == "cam-a"
    assert events[0]["tamper_type"] == "blur"
    assert events[0]["hmac_valid"] == 0


def test_log_crisis_event_roundtrip():
    row_id = db.log_crisis_event(
        session_id="sess-1",
        camera_id="cam-a",
        timestamp=time.time(),
        frame_index=42,
        fire=True,
        smoke=False,
        person=True,
        fall=False,
        confidence=0.87,
        decision="ALERT_FIRE_STATION",
        severity="HIGH",
    )
    assert row_id is not None and row_id > 0

    events = db.get_recent_crisis_events(limit=10)
    assert len(events) == 1
    assert events[0]["fire"] == 1
    assert events[0]["decision"] == "ALERT_FIRE_STATION"
    assert events[0]["confidence"] == pytest.approx(0.87, abs=1e-3)


def test_correlated_events_share_session():
    sid = "sess-corr"
    ts = time.time()
    db.log_tamper_event(session_id=sid, camera_id="cam-b",
                        timestamp=ts, tamper_type="shake",
                        reason="mag=6.1", hmac_valid=True)
    db.log_crisis_event(session_id=sid, camera_id="cam-b",
                        timestamp=ts + 1, frame_index=10,
                        fire=False, smoke=False, person=True, fall=True,
                        confidence=0.72, decision="ALERT_AMBULANCE", severity="MEDIUM")

    corr = db.get_correlated_events(sid)
    assert corr["session_id"] == sid
    assert len(corr["tamper_events"]) == 1
    assert len(corr["crisis_events"]) == 1
