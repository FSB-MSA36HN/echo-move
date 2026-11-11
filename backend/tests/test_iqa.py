import cv2
import numpy as np
import pytest

from echo_move.iqa import compute_iqa, piqe_full


def _prep(img_u8):
    return img_u8, img_u8.astype(np.float64) / 255.0


def _textured(seed=0):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 256, (240, 320), dtype=np.uint8)
    return cv2.GaussianBlur(base, (3, 3), 0)


def test_blur_lowers_sharpness_score():
    sharp = _textured()
    blurred = cv2.GaussianBlur(sharp, (15, 15), 5)
    assert compute_iqa(*_prep(sharp)).blur > compute_iqa(*_prep(blurred)).blur


def test_dark_image_has_low_exposure():
    dark = np.full((120, 160), 5, np.uint8)
    assert compute_iqa(*_prep(dark)).exposure < 10


def test_uniform_image_has_zero_contrast():
    flat = np.full((120, 160), 128, np.uint8)
    assert compute_iqa(*_prep(flat)).contrast == pytest.approx(0, abs=1e-6)


def test_scores_within_range():
    r = compute_iqa(*_prep(_textured()), compute_full=True)
    for v in (r.piqe, r.piqe_full, r.blur, r.contrast, r.noise, r.exposure, r.overall):
        assert 0 <= v <= 100


def test_piqe_full_flat_image_returns_100():
    assert piqe_full(np.full((64, 64), 0.5)) == 100.0
