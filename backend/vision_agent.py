from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
import cv2
from dotenv import load_dotenv

from pipeline_support import (
    DEFAULT_CAMERA_ID,
    VisionEvent,
    create_vision_event,
    get_env_float,
    get_env_int,
    log_payload,
    normalize_video_source,
)


load_dotenv()


DEFAULT_VIDEO_SOURCE = os.getenv("CRISIS_VIDEO_SOURCE", "0")
DEFAULT_FIRE_MODEL_NAME = "best.pt"
DEFAULT_PERSON_MODEL_NAME = "yolov8n.pt"
FIRE_CLASS_ID = get_env_int("FIRE_CLASS_ID", 0)
SMOKE_CLASS_ID = get_env_int("SMOKE_CLASS_ID", 1)

FIRE_CONFIDENCE_THRESHOLD = get_env_float("FIRE_THRESHOLD", 0.75)
SMOKE_CONFIDENCE_THRESHOLD = get_env_float("SMOKE_THRESHOLD", 0.60)
PERSON_CONFIDENCE_THRESHOLD = get_env_float("PERSON_THRESHOLD", 0.55)
PERSON_MIN_BOX_AREA = get_env_int("PERSON_MIN_BOX_AREA", 3000)
MIN_BOX_AREA = get_env_int("MIN_BOX_AREA", 500)
MIN_FIRE_BOX_AREA = get_env_int("FIRE_MIN_BOX_AREA", 250)
MAX_FIRE_BOX_AREA = get_env_int("FIRE_MAX_BOX_AREA", 2000)
MIN_SMOKE_BOX_AREA = get_env_int("SMOKE_MIN_BOX_AREA", 500)
MAX_SMOKE_BOX_AREA = get_env_int("SMOKE_MAX_BOX_AREA", 15000)
MIN_FIRE_ASPECT_RATIO = get_env_float("FIRE_MIN_ASPECT_RATIO", 0.20)
MAX_FIRE_ASPECT_RATIO = get_env_float("FIRE_MAX_ASPECT_RATIO", 1.50)
MIN_SMOKE_ASPECT_RATIO = get_env_float("SMOKE_MIN_ASPECT_RATIO", 0.20)
MAX_SMOKE_ASPECT_RATIO = get_env_float("SMOKE_MAX_ASPECT_RATIO", 2.50)
INFERENCE_IMAGE_SIZE = 960
MOTION_THRESHOLD = get_env_float("MOTION_THRESHOLD", 0.02)

PERSON_CLASS_ID = 0
FIRE_COLOR = (0, 0, 255)
SMOKE_COLOR = (0, 165, 255)
PERSON_COLOR = (255, 0, 0)
FALL_COLOR = (0, 0, 255)
WINDOW_NAME = "Vision Agent"

logger = logging.getLogger(__name__)

_FIRE_MODEL_BUNDLE: tuple[Any, list[int], list[int], str] | None = None
_PERSON_MODEL: Any | None = None
_PREV_GRAY_FRAMES: dict[str, Any] = {}


def _resolve_model_path(env_var_name: str, default_name: str) -> Path:
    configured_path = os.getenv(env_var_name)
    if configured_path:
        return Path(configured_path).expanduser()

    model_dir = os.getenv("MODEL_DIR")
    if model_dir:
        return Path(model_dir).expanduser() / default_name

    return Path(default_name)


def _parse_model_catalog(raw_catalog: str) -> dict[str, str]:
    catalog: dict[str, str] = {}
    for chunk in raw_catalog.split(";"):
        entry = chunk.strip()
        if not entry or ":" not in entry:
            continue
        name, path = entry.split(":", 1)
        catalog[name.strip()] = path.strip()
    return catalog


def _resolve_fire_model_path() -> Path:
    active_model = os.getenv("ACTIVE_FIRE_MODEL", "").strip()
    catalog = _parse_model_catalog(os.getenv("FIRE_MODEL_CATALOG", ""))

    if active_model:
        if active_model in catalog:
            return Path(catalog[active_model]).expanduser()
        return Path(active_model).expanduser()

    return _resolve_model_path("FIRE_MODEL_PATH", DEFAULT_FIRE_MODEL_NAME)


def _load_model(path: Path, env_var_name: str):
    if not path.exists():
        raise RuntimeError(
            f"Model file '{path}' was not found. "
            f"Set {env_var_name} or MODEL_DIR to point to the model."
        )

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is required to run the vision pipeline.") from exc

    try:
        return YOLO(str(path))
    except Exception as exc:
        import sys
        print(f"ERROR: Failed to load model '{path}': {exc}", file=sys.stderr)
        sys.exit(1)


def _get_fire_model_bundle() -> tuple[Any, list[int], list[int], str]:
    global _FIRE_MODEL_BUNDLE
    if _FIRE_MODEL_BUNDLE is not None:
        return _FIRE_MODEL_BUNDLE

    model_path = _resolve_fire_model_path()
    model = _load_model(model_path, "FIRE_MODEL_PATH")
    
    if hasattr(model, 'names'):
        raw_class_names = model.names
    elif hasattr(model, 'model') and hasattr(model.model, 'names'):
        raw_class_names = model.model.names
    else:
        raw_class_names = {0: "fire", 1: "smoke"}
        
    class_names = (
        raw_class_names
        if isinstance(raw_class_names, dict)
        else {index: name for index, name in enumerate(raw_class_names)}
    )
    fire_classes = [FIRE_CLASS_ID]
    smoke_classes = [SMOKE_CLASS_ID]

    log_payload(
        logger,
        logging.INFO,
        "model_loaded",
        {
            "model_type": "fire",
            "path": str(model_path),
            "fire_classes": fire_classes,
            "smoke_classes": smoke_classes,
        },
    )

    _FIRE_MODEL_BUNDLE = (model, fire_classes, smoke_classes, str(model_path))
    return _FIRE_MODEL_BUNDLE


def reset_model_cache() -> None:
    global _FIRE_MODEL_BUNDLE, _PERSON_MODEL
    _FIRE_MODEL_BUNDLE = None
    _PERSON_MODEL = None


def set_active_fire_model(model_reference: str) -> None:
    os.environ["ACTIVE_FIRE_MODEL"] = model_reference
    reset_model_cache()


def _get_person_model():
    global _PERSON_MODEL
    if _PERSON_MODEL is not None:
        return _PERSON_MODEL

    model_path = _resolve_model_path("PERSON_MODEL_PATH", DEFAULT_PERSON_MODEL_NAME)
    _PERSON_MODEL = _load_model(model_path, "PERSON_MODEL_PATH")
    log_payload(
        logger,
        logging.INFO,
        "model_loaded",
        {
            "model_type": "person",
            "path": str(model_path),
        },
    )
    return _PERSON_MODEL


def event_to_crisis(event: VisionEvent | dict) -> str:
    fire_risk = event["fire"] or event["smoke"]
    medical_risk = event["fall_detected"]

    if fire_risk and medical_risk:
        return "BOTH"
    if fire_risk:
        return "FIRE"
    if medical_risk:
        return "MEDICAL"
    return "SAFE"


def box_area(box_coordinates) -> int:
    x1, y1, x2, y2 = map(int, box_coordinates)
    return max(0, x2 - x1) * max(0, y2 - y1)


def box_aspect_ratio(box_coordinates) -> float:
    x1, y1, x2, y2 = map(int, box_coordinates)
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)
    return width / height


def draw_box(frame, box_coordinates, label: str, color: tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = map(int, box_coordinates)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        frame,
        label,
        (x1, max(y1 - 10, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        color,
        2,
        cv2.LINE_AA,
    )


def is_reasonable_box(
    box_coordinates,
    *,
    min_area: int,
    max_area: int,
    min_aspect_ratio: float,
    max_aspect_ratio: float,
) -> bool:
    area = box_area(box_coordinates)
    aspect_ratio = box_aspect_ratio(box_coordinates)
    return (
        min_area <= area <= max_area
        and min_aspect_ratio <= aspect_ratio <= max_aspect_ratio
    )


def is_fire_color(frame, coords) -> bool:
    x1, y1, x2, y2 = map(int, coords)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hue = hsv_roi[:, :, 0]
    hue_mask = (hue >= 0) & (hue <= 50)
    b, g, r = cv2.split(roi)
    red_dominant = (r > b) & (r > g)
    fire_pixels = hue_mask & red_dominant
    fire_ratio = np.sum(fire_pixels) / (roi.shape[0] * roi.shape[1] + 1e-6)
    return fire_ratio > 0.01

def is_smoke_color(frame, coords) -> bool:
    """Smoke should appear as grayish, low-saturation, and dark.
    Reject bright/uniform-colored regions like plain walls."""
    x1, y1, x2, y2 = map(int, coords)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    sat = hsv_roi[:, :, 1]  # saturation channel
    val = hsv_roi[:, :, 2]  # brightness channel
    # Real smoke: low saturation (grayish), not overly bright (not white wall)
    low_sat_pixels = np.sum(sat < 60)
    total_pixels = roi.shape[0] * roi.shape[1] + 1e-6
    low_sat_ratio = low_sat_pixels / total_pixels
    mean_brightness = float(np.mean(val))
    # Accept if >40% of pixels are grayish AND not a pure bright white wall
    return low_sat_ratio > 0.40 and mean_brightness < 220


def compute_roi_motion(frame_gray, prev_gray, coords) -> float:
    x1, y1, x2, y2 = map(int, coords)
    diff = cv2.absdiff(frame_gray[y1:y2, x1:x2], prev_gray[y1:y2, x1:x2])
    return float(cv2.mean(diff)[0])


def detect_fire_and_smoke(frame, event: VisionEvent, camera_id: str) -> float:
    fire_model, fire_classes, smoke_classes, _ = _get_fire_model_bundle()
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prev_gray = _PREV_GRAY_FRAMES.get(camera_id)
    _PREV_GRAY_FRAMES[camera_id] = frame_gray

    results = fire_model.predict(
        frame,
        conf=min(FIRE_CONFIDENCE_THRESHOLD, SMOKE_CONFIDENCE_THRESHOLD),
        imgsz=INFERENCE_IMAGE_SIZE,
        verbose=False,
    )
    
    max_fire_confidence = 0.0
    max_smoke_confidence = 0.0
    
    for result in results:
        for box in result.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            coords = box.xyxy[0]
            x1, y1, x2, y2 = map(int, coords)
            w, h = x2 - x1, y2 - y1

            if cls == FIRE_CLASS_ID:
                if conf < FIRE_CONFIDENCE_THRESHOLD:
                    continue
                if w * h < MIN_BOX_AREA:
                    continue
                if not is_fire_color(frame, coords):
                    continue
                if prev_gray is not None:
                    motion = compute_roi_motion(frame_gray, prev_gray, coords)
                    if motion < MOTION_THRESHOLD:
                        continue
                
                max_fire_confidence = max(max_fire_confidence, conf)
                event["fire"] = True
                draw_box(frame, coords, f"fire {conf:.2f}", FIRE_COLOR)
                
            elif cls == SMOKE_CLASS_ID:
                if conf < SMOKE_CONFIDENCE_THRESHOLD:
                    continue
                if w * h < MIN_BOX_AREA:
                    continue
                # Motion check: static walls won't move
                if prev_gray is not None:
                    motion = compute_roi_motion(frame_gray, prev_gray, coords)
                    if motion < MOTION_THRESHOLD:
                        continue
                # Color check: real smoke is gray/dark, not a bright uniform wall
                if not is_smoke_color(frame, coords):
                    continue

                max_smoke_confidence = max(max_smoke_confidence, conf)
                event["smoke"] = True
                draw_box(frame, coords, f"smoke {conf:.2f}", SMOKE_COLOR)

    event["fire_confidence"] = max_fire_confidence
    event["smoke_confidence"] = max_smoke_confidence
    event["raw_fire_detected"] = event["fire"]
    event["raw_smoke_detected"] = event["smoke"]
    return max(max_fire_confidence, max_smoke_confidence)


def detect_person_and_fall(frame, event: VisionEvent) -> tuple[float, list]:
    person_model = _get_person_model()
    results = person_model.predict(
        frame,
        classes=[PERSON_CLASS_ID],
        conf=PERSON_CONFIDENCE_THRESHOLD,
        imgsz=INFERENCE_IMAGE_SIZE,
        verbose=False,
    )

    max_conf = 0.0
    person_boxes = []
    for result in results:
        for box in result.boxes:
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            w = x2 - x1
            h = y2 - y1

            # Strict filters to remove non-human detections
            if conf < PERSON_CONFIDENCE_THRESHOLD:
                continue
            # Must be large enough to be a real person
            if w * h < PERSON_MIN_BOX_AREA:
                continue
            # Aspect ratio: persons are taller than wide (except when fallen)
            # Allow up to 2.5:1 width-to-height only (very wide boxes = non-person)
            aspect = w / (h + 1e-6)
            if aspect > 2.5:
                continue

            max_conf = max(max_conf, conf)
            event["person"] = True
            person_boxes.append((x1, y1, x2, y2))

            # Fall: person lying down — width > height but within reason
            is_fall = 1.2 < aspect <= 2.5
            if is_fall:
                event["fall_detected"] = True

            label = "fall" if is_fall else "person"
            color = FALL_COLOR if is_fall else PERSON_COLOR
            draw_box(frame, (x1, y1, x2, y2), f"{label} {conf:.2f}", color)

    return max_conf, person_boxes


def process_frame(
    frame,
    camera_id: str = DEFAULT_CAMERA_ID,
    frame_index: int = 0,
) -> VisionEvent:
    event = create_vision_event(camera_id=camera_id, frame_index=frame_index)

    person_confidence = 0.0
    fire_confidence = 0.0

    if "fire" in camera_id.lower():
        fire_confidence = detect_fire_and_smoke(frame, event, camera_id)
    elif "fall" in camera_id.lower() or "person" in camera_id.lower():
        person_confidence, _ = detect_person_and_fall(frame, event)
    else:
        person_confidence, _ = detect_person_and_fall(frame, event)
        fire_confidence = detect_fire_and_smoke(frame, event, camera_id)

    event["confidence"] = max(person_confidence, fire_confidence)
    log_payload(logger, logging.DEBUG, "vision_event", event)
    return event


vision_agent = process_frame


def run_video(video_source: str = DEFAULT_VIDEO_SOURCE) -> None:
    cap = cv2.VideoCapture(normalize_video_source(video_source))
    if not cap.isOpened():
        raise RuntimeError(f"Unable to open video source: {video_source}")

    frame_index = 0
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            process_frame(frame, frame_index=frame_index)
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) == 27:
                break
            frame_index += 1
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run_video(DEFAULT_VIDEO_SOURCE)
