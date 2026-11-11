"""Measure PIQE fast vs full speed and correlation on synthetic or user frames.

Usage: python scripts/benchmark.py [video.mp4] [--frames 200]
Requires: pip install -e backend
"""
import argparse
import time

import cv2
import numpy as np

from echo_move.iqa.metrics import mscn_quality
from echo_move.iqa.piqe import piqe_full


def frames(path, n):
    if path:
        cap = cv2.VideoCapture(path)
        while n and cap.isOpened():
            ok, f = cap.read()
            if not ok:
                break
            yield cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (320, 240))
            n -= 1
    else:
        rng = np.random.default_rng(0)
        for i in range(n):
            base = cv2.GaussianBlur(rng.integers(0, 256, (240, 320), np.uint8), (3, 3), i % 15 + 1)
            yield base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?")
    ap.add_argument("--frames", type=int, default=200)
    a = ap.parse_args()
    fast, full, tf, tl = [], [], [], []
    for g in frames(a.video, a.frames):
        gf = g.astype(np.float64) / 255
        t = time.perf_counter(); fast.append(mscn_quality(gf)); tf.append(time.perf_counter() - t)
        t = time.perf_counter(); full.append(piqe_full(gf)); tl.append(time.perf_counter() - t)
    r = np.corrcoef(fast, full)[0, 1]
    print(f"frames={len(fast)}  fast={np.mean(tf)*1e3:.2f} ms  full={np.mean(tl)*1e3:.2f} ms  "
          f"speedup={np.mean(tl)/np.mean(tf):.1f}x  corr r={r:.3f}")


if __name__ == "__main__":
    main()
