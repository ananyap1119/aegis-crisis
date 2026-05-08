# Aegis-Crisis

**Unified Tamper-Resistant Surveillance & AI Crisis Response Platform**

Aegis-Crisis merges two independent systems into a single production-ready pipeline:

- **[Aegis](https://github.com/Mohiee661/Aegis-Tamper-Resistant-Surveillance-System)** — tamper detection, HMAC frame integrity watermarking, and CLAHE glare rescue
- **[AI Crisis Response](https://github.com/Mohiee661/ai-crisis-response)** — YOLO-based fire/fall detection, LangGraph multi-agent decision engine, social-signal fusion

Only frames that pass Aegis's integrity checks are forwarded to the crisis detection pipeline, eliminating false alarms caused by tampered or corrupted feeds.

---

## How It Works

```
┌─────────────┐
│ Camera Feed │
└──────┬──────┘
       │ raw frame
       ▼
┌──────────────────────────────────────────────┐
│              Aegis Tamper Agent              │
│  ① Blur detection    (Laplacian variance)   │
│  ② Shake detection   (dense optical flow)   │
│  ③ Reposition detect (sustained shift)      │
│  ④ HMAC watermark    (per-second token)     │
│  ⑤ CLAHE glare rescue (pre-processing)      │
└──────┬───────────────────────────────────────┘
       │ tampered → log tamper_events DB, SKIP frame
       │ clean    → CLAHE-rescued frame
       ▼
┌──────────────────────────────────────────────┐
│           AI Crisis Vision Agent             │
│  • Fire & smoke detection  (custom YOLO)    │
│  • Person & fall detection (YOLOv8n)        │
│  • Temporal event stabilization             │
└──────┬───────────────────────────────────────┘
       ▼
┌──────────────────────────────────────────────┐
│         LangGraph Decision Engine            │
│  fusion_agent → risk_agent →                │
│  decision_agent → action_agent              │
│  + Social signal fusion (Groq LLM)          │
└──────┬───────────────────────────────────────┘
       ▼
┌──────────────────────────────────────────────┐
│    Unified Flask-SocketIO Dashboard          │
│  • REST API   (port 5000)                   │
│  • WebSocket  (/stream namespace)           │
│  • React/TS frontend + Integrity Panel      │
└──────────────────────────────────────────────┘
```

Events from the tamper and crisis pipelines are written to a **shared SQLite database** and linked by `session_id`, enabling full forensic correlation across both systems.

---

## Features

### Tamper Detection (Aegis)
| Check | Method | Action on Detection |
|-------|--------|---------------------|
| Blur | Laplacian variance < threshold | Skip frame, log |
| Shake | Dense optical-flow magnitude | Skip frame, log |
| Camera reposition | Sustained directional shift | Skip frame, log |
| HMAC watermark | Per-second HMAC-SHA256 token embedded as RGB pixel | Skip frame, log |
| Glare | Histogram "loss of detail" metric | Apply CLAHE rescue |

### Crisis Detection (AI Crisis Response)
| Hazard | Model | Notes |
|--------|-------|-------|
| Fire | Custom YOLO (`best.pt`) | Color + motion + temporal validation |
| Smoke | Custom YOLO (`best.pt`) | Saturation + motion filter |
| Person | YOLOv8n | Size + aspect-ratio filter |
| Fall | YOLOv8n | Width > height aspect ratio |

### Decision Engine (LangGraph)
- **Fusion agent** — corroborates vision with social signals (Groq LLM or deterministic fallback)
- **Risk agent** — severity assessment with history
- **Decision agent** — maps danger type to action
- **Action agent** — dispatches `ALERT_FIRE_STATION` / `ALERT_AMBULANCE` / `ALERT_BOTH`

### Dashboard
- React/TypeScript frontend (Vite + TailwindCSS + shadcn/ui)
- **Integrity Panel** — per-camera tamper status badge (green = clean, red = tampered), HMAC verification indicator, scrollable tamper event log
- Crisis feed with `(tamper-verified)` provenance context
- Real-time SocketIO updates: `crisis_update` and `tamper_update` events

---

## Project Structure

```
aegis-crisis/
├── backend/
│   ├── vision_agent.py           from ai-crisis-response (unchanged)
│   ├── tamper_agent.py           NEW — wraps full Aegis tamper pipeline
│   ├── decision_engine.py        from ai-crisis-response
│   ├── alert_system.py           from ai-crisis-response
│   ├── social_agent.py           from ai-crisis-response
│   ├── pipeline_support.py       extended with tamper_status field
│   ├── db.py                     NEW — unified SQLite helpers
│   ├── unified_server.py         NEW — merged Flask-SocketIO on port 5000
│   ├── tamper_detector.py        from Aegis
│   ├── watermark_embedder.py     from Aegis
│   ├── watermark_extractor.py    from Aegis
│   ├── watermark_validator.py    from Aegis
│   ├── glare_rescue.py           from Aegis
│   └── pocketsphinx_recognizer.py from Aegis (optional audio logging)
├── frontend/                     React app (crisis-command-glow-main)
│   └── src/
│       ├── components/crisis/
│       │   ├── IntegrityPanel.tsx  NEW — Aegis integrity UI panel
│       │   ├── AlertsPanel.tsx
│       │   ├── AgentTimeline.tsx
│       │   ├── VideoFeed.tsx
│       │   ├── Header.tsx
│       │   ├── MetricsStrip.tsx
│       │   └── StatusBadge.tsx
│       ├── hooks/use-status.ts   updated — polls port 5000, merges tamper data
│       └── lib/types.ts          extended with TamperEvent, CameraIntegrityStatus
├── tests/
│   ├── test_integration_pipeline.py  NEW — 2 required integration tests
│   ├── test_db.py                    NEW — unified DB CRUD tests
│   ├── test_watermark.py             ported from Aegis
│   ├── test_tamper_detector.py       ported from Aegis
│   ├── test_decision_engine.py       ported from ai-crisis-response
│   ├── test_fusion_logic.py          ported from ai-crisis-response
│   ├── test_vision_event.py          ported from ai-crisis-response
│   ├── test_social_agent.py          ported from ai-crisis-response
│   └── test_temporal_tracker.py      ported from ai-crisis-response
├── scripts/                      Aegis utility scripts
├── storage/                      Aegis liveness videos & glare images
├── data/                         SQLite database lives here
├── main_unified.py               Entry point
├── conftest.py                   pytest sys.path setup
├── requirements.txt              Merged & deduplicated
├── .env.example                  All keys from both projects
└── README.md
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/ananyap1119/aegis-crisis
cd aegis-crisis
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — at minimum set GROQ_API_KEY and model paths
```

### 3. Run the backend

```bash
# Webcam (HMAC disabled — camera has no embedder)
python main_unified.py --no-hmac

# Run all videos in videos/ folder sequentially
python main_unified.py --playlist --no-hmac

# With HMAC enabled (camera must embed watermarks via Aegis embedder)
python main_unified.py --video 0
```

The server starts on **http://localhost:5000**.

### 4. Run the frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:5173
```

### 5. Run tests

```bash
pytest -q        # 27 tests, all passing
```

---

## API Reference

All endpoints served by the unified Flask-SocketIO server on port **5000**.

### REST

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | System health, active cameras, latest tamper alerts, current decision lifecycle |
| `GET` | `/api/crisis_events` | Paginated crisis detections from DB (`?limit=N`) |
| `GET` | `/api/tamper_events` | Paginated tamper incidents from DB (`?limit=N`) |
| `POST` | `/api/start_camera` | Register a camera: `{"camera_id": "cam-0", "session_id": "..."}` |
| `POST` | `/api/reset` | Reset incident state |
| `POST` | `/api/override` | Manual operator override: `{"action": "ALERT_FIRE_STATION"}` |

### WebSocket (`/stream` namespace)

| Event | Direction | Payload |
|-------|-----------|---------|
| `crisis_update` | server → client | `{camera_id, session_id, fire, smoke, person, fall, confidence, decision, severity, tamper_verified}` |
| `tamper_update` | server → client | `{camera_id, session_id, tamper_type, reason, hmac_valid, timestamp}` |

---

## Database Schema

**`tamper_events`** — one row per tamper detection

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | TEXT | Shared key with `crisis_events` |
| `camera_id` | TEXT | |
| `timestamp` | REAL | Unix epoch |
| `tamper_type` | TEXT | `blur` / `shake` / `reposition` / `hmac` / `clean` |
| `reason` | TEXT | Human-readable detail |
| `hmac_valid` | INTEGER | 0 = failed, 1 = passed |

**`crisis_events`** — one row per LangGraph decision cycle

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | TEXT | Shared key with `tamper_events` |
| `camera_id` | TEXT | |
| `timestamp` | REAL | Unix epoch |
| `frame_index` | INTEGER | |
| `fire` / `smoke` / `person` / `fall` | INTEGER | Boolean flags |
| `confidence` | REAL | Model confidence |
| `decision` | TEXT | `ALERT_FIRE_STATION` / `ALERT_AMBULANCE` / `ALERT_BOTH` / `NO_ACTION` |
| `severity` | TEXT | `LOW` / `MEDIUM` / `HIGH` / `CRITICAL` |

Both tables are linked by `session_id`. Use `db.get_correlated_events(session_id)` to retrieve all tamper and crisis events for a single camera run.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(required)* | Groq API key for LLM fusion |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model ID |
| `CRISIS_VIDEO_SOURCE` | `0` | Camera index or video file path |
| `CRISIS_LOCATION` | `demo-site` | Location label for alerts |
| `FIRE_MODEL_PATH` | `best.pt` | Custom YOLO fire/smoke model |
| `PERSON_MODEL_PATH` | `yolov8n.pt` | YOLOv8n person model |
| `HMAC_SECRET_KEY` | `AegisSecureWatermarkKey2025` | HMAC watermark secret |
| `DB_PATH` | `data/aegis_crisis.db` | SQLite database path |
| `DEMO_MODE` | `false` | Auto-scan `videos/` folder |

Full list in [.env.example](.env.example).

---

## Integration Tests

Two tests in `tests/test_integration_pipeline.py` verify the core guarantee of the system:

```
test_tampered_frame_skipped_by_crisis_pipeline
  → A solid-black (blurry) frame is detected as tampered
  → process_frame() is never called
  → tamper_events DB has 1 row; crisis_events DB has 0 rows

test_clean_fire_frame_produces_correlated_db_entries
  → A clean frame with fire detected passes tamper check
  → Both tamper_events and crisis_events have 1 row
  → Both rows share the same session_id
  → crisis_events.decision == "ALERT_FIRE_STATION"
```

---

## Credits

Built by integrating:
- **Aegis Tamper-Resistant Surveillance System** by [@Mohiee661](https://github.com/Mohiee661)
- **AI Crisis Response** by [@Mohiee661](https://github.com/Mohiee661)
