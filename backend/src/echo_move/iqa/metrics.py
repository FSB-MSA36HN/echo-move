"""Five image-quality metrics (all scaled to 0-100, higher = better).

References:
    Blur      — Pech-Pacheco et al., 2000 (variance of Laplacian)
    Noise     — Immerkaer, 1996 (residual after smoothing)
    Contrast  — Peli, 1990 (RMS contrast)
    PIQE      — Venkatanath et al., 2015
    Exposure  — ISO 18434-1 (clipped pixel ratio)
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from ..config import PiqeMode
from .piqe import mscn, piqe_full

log = logging.getLogger(__name__)


@dataclass
class IqaResult:
    piqe: float = 0.0
    piqe_full: float = 0.0
    blur: float = 0.0
    contrast: float = 0.0
    noise: float = 0.0
    exposure: float = 0.0
    overall: float = 0.0
    brightness: float = 0.0
    time_fast_ms: float = 0.0
    time_full_ms: float = 0.0
    time_total_ms: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in asdict(self).items()}


def mscn_quality(gray_f: np.ndarray) -> float:
    """Fast global quality proxy: 100 - 100*std(MSCN). (Not the full PIQE.)"""
    return max(100.0 - float(np.std(mscn(gray_f))) * 100.0, 0.0)


def blur_score(gray_u8: np.ndarray) -> float:
    return min(float(cv2.Laplacian(gray_u8, cv2.CV_64F).var()) / 10.0, 100.0)


def contrast_score(gray_f: np.ndarray) -> float:
    return min(float(np.std(gray_f)) * 400.0, 100.0)


def noise_score(gray_f: np.ndarray) -> float:
    residual = gray_f - cv2.GaussianBlur(gray_f, (5, 5), 0)
    return max(100.0 - float(np.std(residual)) * 1000.0, 0.0)


def exposure_score(gray_f: np.ndarray) -> float:
    over = float(np.count_nonzero(gray_f > 0.95)) / gray_f.size
    under = float(np.count_nonzero(gray_f < 0.05)) / gray_f.size
    return max(100.0 - (over + under) * 1000.0, 0.0)


def compute_iqa(
    gray_u8: np.ndarray,
    gray_f: np.ndarray,
    *,
    mode: PiqeMode = "both",
    weights: tuple[float, float, float, float, float] = (0.25, 0.25, 0.20, 0.15, 0.15),
    compute_full: bool = False,
) -> IqaResult:
    """Compute all metrics for one frame. ``compute_full`` enables the slow block PIQE."""
    t0 = time.perf_counter()
    try:
        t = time.perf_counter()
        fast = mscn_quality(gray_f)
        time_fast = (time.perf_counter() - t) * 1000

        full, time_full = fast, 0.0
        if compute_full or mode == "full":
            t = time.perf_counter()
            full = piqe_full(gray_f)
            time_full = (time.perf_counter() - t) * 1000

        blur = blur_score(gray_u8)
        contrast = contrast_score(gray_f)
        noise = noise_score(gray_f)
        exposure = exposure_score(gray_f)
        piqe = full if mode == "full" else fast
        w = weights
        overall = w[0] * piqe + w[1] * blur + w[2] * contrast + w[3] * noise + w[4] * exposure
        return IqaResult(
            piqe, full, blur, contrast, noise, exposure, overall,
            float(np.mean(gray_u8)), time_fast, time_full,
            (time.perf_counter() - t0) * 1000,
        )
    except Exception:
        log.exception("compute_iqa failed")
        return IqaResult()
