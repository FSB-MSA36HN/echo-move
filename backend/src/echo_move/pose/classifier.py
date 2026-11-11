"""Rule-based per-frame posture classification from COCO-17 keypoints.

Keypoints are normalised (x / width, y / height, confidence). ``aspect`` (width / height)
restores true angles, otherwise a 16:9 frame would distort the spine angle by ~40 %.
Temporal confirmation (how long a posture lasts) lives in ``alerts.engine``.
"""

from __future__ import annotations

import math
from typing import Any

from ..config import Settings

L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 5, 6, 11, 12
L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 13, 14, 15, 16

GREEN: list[float] = [0, 1, 0]
ORANGE: list[float] = [1, 0.65, 0]
RED: list[float] = [1, 0, 0]


def _result(
    level: str, color: list[float], label: str, detail: str, technique: str, **metrics: float
) -> dict[str, Any]:
    out: dict[str, Any] = {"level": level, "color": color, "label": label,
                           "detail": detail, "technique": technique}
    out.update({k: round(v, 1) for k, v in metrics.items()})
    return out


def joint_angle(p1: list[float], p2: list[float], p3: list[float]) -> float:
    """Angle at ``p2`` (degrees) formed by p1-p2-p3."""
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / ((math.hypot(*v1) + 1e-6) * (math.hypot(*v2) + 1e-6))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def body_bbox(kps: list[list[float]], vis: float) -> tuple[float, float, float, float] | None:
    pts = [(k[0], k[1]) for k in kps if k[2] > vis]
    if len(pts) < 2:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def classify_posture(
    kps: list[list[float]], cfg: Settings, aspect: float = 1.0
) -> dict[str, Any]:
    safe = _result("SAFE", GREEN, "AN TOÀN", "Bình thường", "NONE")
    if not kps or len(kps) < 17:
        return safe
    vis = cfg.visibility_threshold
    if not all(kps[i][2] > vis for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)):
        return _result("SAFE", GREEN, "AN TOÀN", "Không đủ điểm", "NONE")
    pts = [[k[0] * aspect, k[1], k[2]] for k in kps]

    sx = (pts[L_SHOULDER][0] + pts[R_SHOULDER][0]) / 2
    sy = (pts[L_SHOULDER][1] + pts[R_SHOULDER][1]) / 2
    hx = (pts[L_HIP][0] + pts[R_HIP][0]) / 2
    hy = (pts[L_HIP][1] + pts[R_HIP][1]) / 2
    spine = math.degrees(math.atan2(abs(sx - hx), abs(sy - hy) + 1e-6))

    leg_ids = (L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)
    if all(pts[i][2] > vis for i in leg_ids):
        knee = (
            joint_angle(pts[L_HIP], pts[L_KNEE], pts[L_ANKLE])
            + joint_angle(pts[R_HIP], pts[R_KNEE], pts[R_ANKLE])
        ) / 2
    else:
        knee = 180.0

    box = body_bbox(pts, vis)
    ratio = (box[2] - box[0]) / max(box[3] - box[1], 1e-6) if box else 0.0
    m = {"spine_deg": spine, "knee_deg": knee, "bbox_ratio": ratio}

    if spine > cfg.fall_spine_deg and ratio > cfg.fall_bbox_ratio:
        return _result("RISK", RED, "PHÁT HIỆN NGÃ", "Nằm trên sàn", "FALL", **m)
    if knee < cfg.knee_bent_deg and spine < cfg.lift_spine_max_deg:
        return _result("SAFE", GREEN, "NÂNG ĐÚNG KỸ THUẬT", f"Gối {knee:.0f}°", "PROPER_LIFT", **m)
    if spine > cfg.spine_risk_deg:
        return _result("RISK", RED, "SAI TƯ THẾ", f"Cúi {spine:.0f}°", "IMPROPER", **m)
    if spine > cfg.spine_safe_deg:
        return _result("WARNING", ORANGE, "CHÚ Ý", f"Cúi {spine:.0f}°", "PARTIAL", **m)
    return _result("SAFE", GREEN, "AN TOÀN", "Bình thường", "NONE", **m)
