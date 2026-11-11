"""Draw skeletons / status on frames for MJPEG streams and alert snapshots."""

from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

EDGES = [(0, 1), (1, 3), (0, 2), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
         (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
BGR = {"SAFE": (80, 200, 60), "WARNING": (0, 165, 255), "RISK": (40, 40, 230)}
# Hershey fonts are ASCII-only, so overlay labels avoid Vietnamese diacritics.
LABELS = {"NONE": "OK", "PROPER_LIFT": "PROPER LIFT", "PARTIAL": "BENDING",
          "IMPROPER": "BAD POSTURE", "FALL": "FALL"}


def annotate(frame: np.ndarray, persons: list[dict[str, Any]], *, title: str = "",
             highlight: int | None = None, vis: float = 0.25) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    for p in persons:
        safety = p.get("safety") or {}
        color = BGR.get(safety.get("level", "SAFE"), BGR["SAFE"])
        thick = 3 if highlight is None or p.get("id") == highlight else 1
        kps = p["keypoints"]
        pts = [(int(k[0] * w), int(k[1] * h), k[2]) for k in kps]
        for a, b in EDGES:
            if pts[a][2] > vis and pts[b][2] > vis:
                cv2.line(out, pts[a][:2], pts[b][:2], color, thick, cv2.LINE_AA)
        for x, y, c in pts:
            if c > vis:
                cv2.circle(out, (x, y), 3 + thick, color, -1, cv2.LINE_AA)
        box = p.get("bbox")
        if box:
            x1, y1, x2, y2 = (int(box[0] * w) - 10, int(box[1] * h) - 10,
                              int(box[2] * w) + 10, int(box[3] * h) + 10)
            cv2.rectangle(out, (x1, y1), (x2, y2), color, thick)
            label = f"#{p.get('id')} {LABELS.get(safety.get('technique', 'NONE'), '')}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(out, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
            cv2.putText(out, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (255, 255, 255), 1, cv2.LINE_AA)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    text = f"{title}  {stamp}" if title else stamp
    cv2.rectangle(out, (0, 0), (w, 24), (0, 0, 0), -1)
    cv2.putText(out, text, (8, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                cv2.LINE_AA)
    return out


def encode_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""
