"""Draw skeletons / status on frames for MJPEG streams and alert snapshots."""

from __future__ import annotations

import time
import unicodedata
from collections.abc import Iterable
from typing import Any

import cv2
import numpy as np

EDGES = [(0, 1), (1, 3), (0, 2), (2, 4), (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),
         (5, 11), (6, 12), (11, 12), (11, 13), (13, 15), (12, 14), (14, 16)]
BGR = {"SAFE": (80, 200, 60), "WARNING": (0, 165, 255), "RISK": (40, 40, 230)}
# Hershey fonts are ASCII-only, so overlay labels avoid Vietnamese diacritics.
LABELS = {"NONE": "OK", "PROPER_LIFT": "PROPER LIFT", "PARTIAL": "BENDING",
          "IMPROPER": "BAD POSTURE", "FALL": "FALL"}


def ascii_text(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def draw_zones(out: np.ndarray, zones: Iterable[Any], active: set[str]) -> None:
    h, w = out.shape[:2]
    layer = out.copy()
    polys = []
    for z in zones:
        pts = np.array([[int(x * w), int(y * h)] for x, y in z.points], np.int32)
        color = (0, 0, 255) if z.name in active else (0, 140, 255)
        cv2.fillPoly(layer, [pts], color)
        polys.append((z, pts, color))
    cv2.addWeighted(layer, 0.25, out, 0.75, 0, out)
    for z, pts, color in polys:
        cv2.polylines(out, [pts], True, color, 2, cv2.LINE_AA)
        x, y = pts[:, 0].min(), pts[:, 1].min()
        cv2.putText(out, ascii_text(z.name), (int(x) + 4, int(y) + 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, color, 1, cv2.LINE_AA)


def annotate(frame: np.ndarray, persons: list[dict[str, Any]], *, title: str = "",
             highlight: int | None = None, vis: float = 0.25,
             zones: Iterable[Any] = ()) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    zones = list(zones)
    if zones:
        active = {z["name"] for p in persons for z in p.get("zones") or []}
        draw_zones(out, zones, active)
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
            missing = [k for k, v in (p.get("ppe") or {}).items() if v is False]
            if missing:
                label += " NO-" + "/".join(m.upper() for m in missing)
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


def blur_faces(frame: np.ndarray, persons: list[dict[str, Any]], vis: float = 0.25) -> np.ndarray:
    """Pixelate each worker's head (from nose/eye/ear keypoints, or above the shoulders) so
    stored snapshots and clips do not keep identifiable faces."""
    out = frame.copy()
    h, w = out.shape[:2]
    for p in persons:
        k = p["keypoints"]
        head = [(k[i][0] * w, k[i][1] * h) for i in range(5) if k[i][2] > vis]
        sh = [(k[i][0] * w, k[i][1] * h) for i in (5, 6) if k[i][2] > vis]
        sh_w = abs(sh[0][0] - sh[1][0]) if len(sh) == 2 else 0.0
        if head:
            cx = sum(x for x, _ in head) / len(head)
            cy = sum(y for _, y in head) / len(head)
            spread = max(max(x for x, _ in head) - min(x for x, _ in head), 1.0)
            r = max(spread * 1.3, sh_w * 0.45, 12.0)
        elif len(sh) == 2:
            cx, cy = (sh[0][0] + sh[1][0]) / 2, (sh[0][1] + sh[1][1]) / 2 - sh_w * 0.6
            r = max(sh_w * 0.5, 12.0)
        else:
            continue
        x1, y1 = max(int(cx - r), 0), max(int(cy - r * 1.2), 0)
        x2, y2 = min(int(cx + r), w), min(int(cy + r), h)
        if x2 - x1 < 2 or y2 - y1 < 2:
            continue
        roi = out[y1:y2, x1:x2]
        small = cv2.resize(roi, (max(1, (x2 - x1) // 10), max(1, (y2 - y1) // 10)),
                           interpolation=cv2.INTER_LINEAR)
        out[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1),
                                       interpolation=cv2.INTER_NEAREST)
    return out


def encode_jpeg(frame: np.ndarray, quality: int = 80) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""
