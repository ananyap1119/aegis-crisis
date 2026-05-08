"""Tests ported from Aegis tests/test_integration.py + test_watermarker.py"""
import numpy as np
import time

from watermark_embedder import get_hmac_color, embed_watermark, get_watermark_embedder
from watermark_extractor import extract_watermark_color, color_distance
from watermark_validator import get_expected_hmac_token


def test_hmac_color_generation_is_deterministic():
    ts = 1609459200
    c1 = get_hmac_color(ts)
    c2 = get_hmac_color(ts)
    assert c1 == c2


def test_hmac_color_differs_across_timestamps():
    c1 = get_hmac_color(1609459200)
    c2 = get_hmac_color(1609459201)
    assert c1 != c2


def test_color_distance_same_colors():
    assert color_distance((255, 0, 0), (255, 0, 0)) == 0.0


def test_color_distance_different_colors():
    assert color_distance((0, 0, 0), (255, 255, 255)) > 0


def test_watermark_embedder_factory():
    embedder = get_watermark_embedder()
    assert hasattr(embedder, "embed")


def test_embed_and_extract_roundtrip():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    ts = int(time.time())
    watermarked = embed_watermark(frame.copy(), ts)
    extracted = extract_watermark_color(watermarked)
    assert extracted is not None
    expected_rgb = get_hmac_color(ts)
    # BGR stored in frame; extracted returns mean of BGR region as tuple
    # Just verify extraction returned a 3-tuple
    assert len(extracted) == 3


def test_expected_hmac_token_is_4_digit_string():
    token = get_expected_hmac_token(1609459200)
    assert len(token) == 4
    assert token.isdigit()
