"""Rule-based posture classification from COCO-17 keypoints.

Keypoints are normalised (x, y in 0-1, confidence); ``frame_h`` is 1.0 in that space.
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
    level: str, color: list[float], label: str, detail: str, technique: str
) -> dict[str, Any]:
    return {"level": level, "color": color, "label": label,
            "detail": detail, "technique": technique}


def joint_angle(p1: list[float], p2: list[float], p3: list[float]) -> float:
    """Angle at ``p2`` (degrees) formed by p1-p2-p3."""
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / ((math.hypot(*v1) + 1e-6) * (math.hypot(*v2) + 1e-6))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def classify_posture(kps: list[list[float]], cfg: Settings, frame_h: float = 1.0) -> dict[str, Any]:
    safe = _result("SAFE", GREEN, "AN TOÀN", "Bình thường", "NONE")
    if not kps or len(kps) < 17:
        return safe
    vis = cfg.visibility_threshold
    if not all(kps[i][2] > vis for i in (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)):
        return _result("SAFE", GREEN, "AN TOÀN", "Không đủ điểm", "NONE")

    sx = (kps[L_SHOULDER][0] + kps[R_SHOULDER][0]) / 2
    sy = (kps[L_SHOULDER][1] + kps[R_SHOULDER][1]) / 2
    hx = (kps[L_HIP][0] + kps[R_HIP][0]) / 2
    hy = (kps[L_HIP][1] + kps[R_HIP][1]) / 2
    spine = math.degrees(math.atan2(abs(sx - hx), abs(sy - hy) + 1e-6))

    leg_ids = (L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)
    if all(kps[i][2] > vis for i in leg_ids):
        knee = (
            joint_angle(kps[L_HIP], kps[L_KNEE], kps[L_ANKLE])
            + joint_angle(kps[R_HIP], kps[R_KNEE], kps[R_ANKLE])
        ) / 2
    else:
        knee = 180.0

    if abs(sy - hy) < frame_h * cfg.fall_torso_ratio:
        return _result("RISK", RED, "PHÁT HIỆN NGÃ", "Nguy hiểm", "FALL")
    if knee < cfg.knee_bent_deg and spine < cfg.lift_spine_max_deg:
        return _result("SAFE", GREEN, "NÂNG ĐÚNG KỸ THUẬT", f"Gối {knee:.0f}°", "PROPER_LIFT")
    if spine > cfg.spine_risk_deg:
        return _result("RISK", RED, "SAI TƯ THẾ", f"Cúi {spine:.0f}°", "IMPROPER")
    if spine > cfg.spine_safe_deg:
        return _result("WARNING", ORANGE, "CHÚ Ý", f"Cúi {spine:.0f}°", "PARTIAL")
    return safe
