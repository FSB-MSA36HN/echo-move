"""Block-wise PIQE approximation (Venkatanath et al., 2015)."""

from __future__ import annotations

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)
BLOCK = 16


def mscn(gray: np.ndarray, ksize: int = 7) -> np.ndarray:
    """Mean-subtracted contrast-normalised coefficients of a [0,1] float image."""
    mu = cv2.GaussianBlur(gray, (ksize, ksize), 0)
    var = cv2.GaussianBlur(gray * gray, (ksize, ksize), 0) - mu * mu
    return (gray - mu) / (np.sqrt(np.maximum(var, 0)) + 1e-3)


def piqe_full(gray: np.ndarray) -> float:
    """Return a 0-100 quality score (higher is better) for a [0,1] float gray image."""
    try:
        pad_h = (BLOCK - gray.shape[0] % BLOCK) % BLOCK
        pad_w = (BLOCK - gray.shape[1] % BLOCK) % BLOCK
        img = np.pad(gray, ((0, pad_h), (0, pad_w)), mode="edge")
        coeffs = mscn(img)
        local_var = np.maximum(
            cv2.boxFilter(coeffs * coeffs, -1, (3, 3)) - cv2.boxFilter(coeffs, -1, (3, 3)) ** 2,
            0,
        )
        rows, cols = img.shape[0] // BLOCK, img.shape[1] // BLOCK
        # Reshape into (rows, cols, BLOCK, BLOCK) blocks — vectorised, no Python loop.
        blocks = coeffs.reshape(rows, BLOCK, cols, BLOCK).swapaxes(1, 2)
        lv_blocks = local_var.reshape(rows, BLOCK, cols, BLOCK).swapaxes(1, 2)
        blk_var = blocks.var(axis=(2, 3)).ravel()
        blk_lv = lv_blocks.mean(axis=(2, 3)).ravel()
        keep = blk_var >= 0.1  # skip flat (uniform) blocks
        if not keep.any():
            return 100.0
        weights = np.where(blk_var[keep] > 0.5, 2.0, 1.0)
        weighted = float(np.sum(blk_lv[keep] * weights) / np.sum(weights))
        return float(np.clip(100 - weighted * 180, 0, 100))
    except Exception:
        log.exception("piqe_full failed")
        return 100.0
