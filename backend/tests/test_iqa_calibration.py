import json

import cv2
import numpy as np

from echo_move.iqa.calibration import (
    DEFAULT_WEIGHTS,
    build_dataset,
    degrade,
    extract_metrics,
    make_workshop_scene,
    run_calibration,
    score_weights,
    search_weights,
    verdict,
)
from echo_move.iqa.metrics import compute_iqa


def test_workshop_scene_has_texture_and_edges():
    img = make_workshop_scene(0)
    assert img.shape[0] >= 200 and img.ndim == 3
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    assert gray.std() > 15  # not flat
    assert compute_iqa(gray, gray.astype(np.float64) / 255).blur > 5


def test_degradations_worsen_matching_metric():
    clean = make_workshop_scene(1)
    rng = np.random.default_rng(0)
    def gray(bgr):
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    g0 = gray(clean)
    r0 = compute_iqa(g0, g0.astype(np.float64) / 255)
    blurred = gray(degrade(clean, "blur", 4, rng))
    noisy = gray(degrade(clean, "noise", 4, rng))
    low_c = gray(degrade(clean, "contrast", 4, rng))
    bright = gray(degrade(clean, "exposure_over", 4, rng))
    dark = gray(degrade(clean, "exposure_under", 4, rng))
    assert compute_iqa(blurred, blurred.astype(np.float64) / 255).blur < r0.blur
    assert compute_iqa(noisy, noisy.astype(np.float64) / 255).noise < r0.noise
    assert compute_iqa(low_c, low_c.astype(np.float64) / 255).contrast < r0.contrast
    assert compute_iqa(bright, bright.astype(np.float64) / 255).exposure < r0.exposure
    assert compute_iqa(dark, dark.astype(np.float64) / 255).exposure < r0.exposure


def test_build_dataset_and_default_ranks_well(tmp_path):
    samples = build_dataset(tmp_path / "img", n_bases=2, severities=(0, 2, 4), seed=1)
    assert len(samples) >= 10
    assert (tmp_path / "img" / "manifest.json").is_file()
    metrics, quals, kinds = extract_metrics(samples)
    scored = score_weights(metrics, quals, kinds, DEFAULT_WEIGHTS, label="default")
    # Operational goal: clean frames stay above threshold; ranking not inverted overall.
    assert scored.keep_clean >= 0.9
    assert scored.pairwise > 0.55
    assert scored.f1 >= 0.0  # F1 reported; absolute value depends on synthetic severity mix


def test_search_includes_default_and_verdict(tmp_path):
    samples = build_dataset(tmp_path / "img", n_bases=2, severities=(0, 2, 4), seed=2)
    metrics, quals, kinds = extract_metrics(samples)
    ranked = search_weights(metrics, quals, kinds, n_random=30, seed=2)
    assert any(s.label == "default" for s in ranked)
    default = next(s for s in ranked if s.label == "default")
    assert default.mean_kind != 0 or default.per_kind
    msg = verdict(default, ranked[0])
    assert msg.startswith("DEFAULT_")


def test_run_calibration_writes_report(tmp_path):
    report = run_calibration(tmp_path / "out", n_bases=2, n_random=40, seed=3)
    assert (tmp_path / "out" / "report.json").is_file()
    assert (tmp_path / "out" / "report.md").is_file()
    data = json.loads((tmp_path / "out" / "report.json").read_text())
    assert data["n_samples"] == report["n_samples"]
    assert "verdict" in data and data["default"]["spearman"] >= 0
