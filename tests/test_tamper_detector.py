"""Tests ported from Aegis tests/test_tamper_detector.py (adapted — no camera)"""
import numpy as np
import cv2

from tamper_detector import check_blur, check_shake, fix_blur_unsharp_mask


def _gray(arr):
    return cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)


def test_sharp_image_not_blurry():
    # Checkerboard has high Laplacian variance
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    frame[::4, :] = 255
    frame[:, ::4] = 255
    gray = _gray(frame)
    is_blurred, variance = check_blur(gray, threshold=25.0)
    assert not is_blurred
    assert variance > 25.0


def test_solid_color_image_is_blurry():
    frame = np.full((64, 64, 3), 128, dtype=np.uint8)
    gray = _gray(frame)
    is_blurred, variance = check_blur(gray, threshold=25.0)
    assert is_blurred
    assert variance < 25.0


def test_no_shake_on_identical_frames():
    frame = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    gray = _gray(frame)
    is_shaken, mag = check_shake(gray, gray, threshold=5.0)
    assert not is_shaken
    assert mag < 5.0


def test_fix_blur_unsharp_mask_returns_same_shape():
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    out = fix_blur_unsharp_mask(frame, kernel_size=5, sigma=1.0, strength=1.5)
    assert out.shape == frame.shape
    assert out.dtype == np.uint8
