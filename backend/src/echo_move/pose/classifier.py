"""Rule-based per-frame posture classification from COCO-17 keypoints.

Keypoints are normalised (x / width, y / height, confidence). ``aspect`` (width / height)
restores true angles, otherwise a 16:9 frame would distort the spine angle by ~40 %.
Temporal confirmation (how long a posture lasts) lives in ``alerts.engine``; the
track-dependent "collapsed vs. standing height" fall signal lives in ``pose.fall``.

Fall signals (multi-signal rule, ``cfg.fall_multisignal``):

* lying     — torso > ``fall_spine_deg`` from vertical and body box wider than tall;
* head_low  — head less than ``head_low_ratio`` × body height above the hips;
* collapsed — body height < ``fall_collapse_ratio`` × the track's standing height.

FALL needs two signals (a lying body whose head is not visible also counts), so a worker
bent over a box (head low only) or sitting on the floor (collapsed only) is not a fall,
while a fall towards the camera (collapsed + head low, torso foreshortened) is.
"""

from __future__ import annotations

import math
from typing import Any

from ..config import Settings

NOSE, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_WRIST, R_WRIST = 0, 5, 6, 7, 8, 9, 10
L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 11, 12, 13, 14, 15, 16
HEAD = (0, 1, 2, 3, 4)

GREEN: list[float] = [0, 1, 0]
ORANGE: list[float] = [1, 0.65, 0]
RED: list[float] = [1, 0, 0]

# REBA tables (Hignett & McAtamney, 2000).
# TABLE_A[trunk-1][neck-1][legs-1], TABLE_B[upper_arm-1][lower_arm-1][wrist-1], TABLE_C[A-1][B-1]
TABLE_A = [
    [[1, 2, 3, 4], [1, 2, 3, 4], [3, 3, 5, 6]],
    [[2, 3, 4, 5], [3, 4, 5, 6], [4, 5, 6, 7]],
    [[2, 4, 5, 6], [4, 5, 6, 7], [5, 6, 7, 8]],
    [[3, 5, 6, 7], [5, 6, 7, 8], [6, 7, 8, 9]],
    [[4, 6, 7, 8], [6, 7, 8, 9], [7, 8, 9, 9]],
]
TABLE_B = [
    [[1, 2, 2], [1, 2, 3]],
    [[1, 2, 3], [2, 3, 4]],
    [[3, 4, 5], [4, 5, 5]],
    [[4, 5, 5], [5, 6, 7]],
    [[6, 7, 8], [7, 8, 8]],
    [[7, 8, 8], [8, 9, 9]],
]
TABLE_C = [
    [1, 1, 1, 2, 3, 3, 4, 5, 6, 7, 7, 7],
    [1, 2, 2, 3, 4, 4, 5, 6, 6, 7, 7, 8],
    [2, 3, 3, 3, 4, 5, 6, 7, 7, 8, 8, 8],
    [3, 4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9],
    [4, 4, 4, 5, 6, 7, 8, 8, 9, 9, 9, 9],
    [6, 6, 6, 7, 8, 8, 9, 9, 10, 10, 10, 10],
    [7, 7, 7, 8, 9, 9, 9, 10, 10, 11, 11, 11],
    [8, 8, 8, 9, 10, 10, 10, 10, 10, 11, 11, 11],
    [9, 9, 9, 10, 10, 10, 11, 11, 11, 12, 12, 12],
    [10, 10, 10, 11, 11, 11, 11, 12, 12, 12, 12, 12],
    [11, 11, 11, 11, 12, 12, 12, 12, 12, 12, 12, 12],
    [12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12, 12],
]


def _result(
    level: str, color: list[float], label: str, detail: str, technique: str,
    extra: dict[str, Any] | None = None, **metrics: float
) -> dict[str, Any]:
    out: dict[str, Any] = {"level": level, "color": color, "label": label,
                           "detail": detail, "technique": technique}
    out.update({k: round(v, 1) for k, v in metrics.items()})
    out.update(extra or {})
    return out


def joint_angle(p1: list[float], p2: list[float], p3: list[float]) -> float:
    """Angle at ``p2`` (degrees) formed by p1-p2-p3."""
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / ((math.hypot(*v1) + 1e-6) * (math.hypot(*v2) + 1e-6))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _vec_angle(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    cos = (v1[0] * v2[0] + v1[1] * v2[1]) / ((math.hypot(*v1) + 1e-6) * (math.hypot(*v2) + 1e-6))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def body_bbox(kps: list[list[float]], vis: float) -> tuple[float, float, float, float] | None:
    pts = [(k[0], k[1]) for k in kps if k[2] > vis]
    if len(pts) < 2:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def head_point(pts: list[list[float]], vis: float) -> tuple[float, float] | None:
    head = [pts[i] for i in HEAD if pts[i][2] > vis]
    if not head:
        return None
    return sum(p[0] for p in head) / len(head), sum(p[1] for p in head) / len(head)


def reba_score(pts: list[list[float]], vis: float, spine: float, knee: float) -> int:
    """Simplified REBA from one 2D frame: trunk, neck, legs, upper/lower arm. Load, coupling,
    twisting and wrist deviation are not observable and are scored as neutral."""
    trunk = 1 if spine <= 5 else 2 if spine <= 20 else 3 if spine <= 60 else 4
    sh = ((pts[L_SHOULDER][0] + pts[R_SHOULDER][0]) / 2,
          (pts[L_SHOULDER][1] + pts[R_SHOULDER][1]) / 2)
    hp = ((pts[L_HIP][0] + pts[R_HIP][0]) / 2, (pts[L_HIP][1] + pts[R_HIP][1]) / 2)
    up = (sh[0] - hp[0], sh[1] - hp[1])
    neck = 1
    hd = head_point(pts, vis)
    if hd is not None and _vec_angle(up, (hd[0] - sh[0], hd[1] - sh[1])) > 20:
        neck = 2
    flex = 180.0 - knee
    legs = 1 + (2 if flex > 60 else 1 if flex >= 30 else 0)
    upper, lower = 1, 1
    down = (-up[0], -up[1])
    for s, e, w in ((L_SHOULDER, L_ELBOW, L_WRIST), (R_SHOULDER, R_ELBOW, R_WRIST)):
        if pts[s][2] <= vis or pts[e][2] <= vis:
            continue
        a = _vec_angle(down, (pts[e][0] - pts[s][0], pts[e][1] - pts[s][1]))
        upper = max(upper, 1 if a <= 20 else 2 if a <= 45 else 3 if a <= 90 else 4)
        if pts[w][2] > vis:
            elbow_flex = 180.0 - joint_angle(pts[s], pts[e], pts[w])
            lower = max(lower, 1 if 60 <= elbow_flex <= 100 else 2)
    score_a = TABLE_A[trunk - 1][neck - 1][legs - 1]
    score_b = TABLE_B[upper - 1][lower - 1][0]
    return TABLE_C[min(score_a, 12) - 1][min(score_b, 12) - 1]


def is_fall(lying: bool, head_low: bool | None, collapsed: bool, cfg: Settings) -> bool:
    if not cfg.fall_multisignal:
        return lying
    if lying and head_low is None:
        return True
    return (int(lying) + int(bool(head_low)) + int(collapsed)) >= 2


FALL_RESULT = ("RISK", RED, "PHÁT HIỆN NGÃ")


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
    height = (box[3] - box[1]) if box else 0.0
    m = {"spine_deg": spine, "knee_deg": knee, "bbox_ratio": ratio}

    lying = spine > cfg.fall_spine_deg and ratio > cfg.fall_bbox_ratio
    hd = head_point(pts, vis)
    head_low = None if hd is None else bool(hy - hd[1] < cfg.head_low_ratio * max(height, 1e-6))
    extra = {"reba": reba_score(pts, vis, spine, knee),
             "signals": {"lying": lying, "head_low": head_low, "collapsed": False},
             "height": round(box[3] - box[1], 4) if box else 0.0,
             "hip_y": round(hy, 4)}

    if is_fall(lying, head_low, False, cfg):
        detail = "Nằm trên sàn" if lying else "Đầu thấp ngang hông"
        level, color, label = FALL_RESULT
        return _result(level, color, label, detail, "FALL", extra, **m)
    if knee < cfg.knee_bent_deg and spine < cfg.lift_spine_max_deg:
        return _result("SAFE", GREEN, "NÂNG ĐÚNG KỸ THUẬT", f"Gối {knee:.0f}°", "PROPER_LIFT",
                       extra, **m)
    if spine > cfg.spine_risk_deg:
        return _result("RISK", RED, "SAI TƯ THẾ", f"Cúi {spine:.0f}°", "IMPROPER", extra, **m)
    if spine > cfg.spine_safe_deg:
        return _result("WARNING", ORANGE, "CHÚ Ý", f"Cúi {spine:.0f}°", "PARTIAL", extra, **m)
    return _result("SAFE", GREEN, "AN TOÀN", "Bình thường", "NONE", extra, **m)
