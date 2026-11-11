"""Temporal alert confirmation.

The per-frame classifier is noisy (occlusion, motion blur, a worker crouching for a second),
so an alert is raised only when a condition persists:

* FALL     — classifier says FALL for ``fall_confirm_s`` (halved after a rapid hip drop).
* POSTURE  — improper bending (IMPROPER) for ``posture_confirm_s``.
* CAMERA   — overall IQA below ``low_quality_threshold`` for ``quality_confirm_s``.

Short dropouts (< ``GRACE_S``) do not reset an episode. Each (type, track) pair fires at
most once per ``alert_cooldown_s``.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import Settings

MESSAGES = {
    "FALL": ("CRITICAL", "Phát hiện công nhân bị ngã"),
    "POSTURE": ("WARNING", "Cúi sai tư thế kéo dài"),
    "CAMERA": ("WARNING", "Chất lượng camera kém / bị che"),
}


@dataclass
class Alert:
    type: str
    level: str
    source: str
    message: str
    detail: str = ""
    track_id: int | None = None
    t: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Episode:
    start: float | None = None
    last_true: float = 0.0
    fired: bool = False


class AlertEngine:
    GRACE_S = 0.5
    FORGET_S = 5.0
    DROP_WINDOW_S = 1.5
    DROP_RATIO = 0.25  # hip falls by > 25 % of body height within DROP_WINDOW_S

    def __init__(self, cfg: Settings, source: str):
        self.cfg = cfg
        self.source = source
        self._episodes: dict[tuple[str, int | None], _Episode] = {}
        self._last_fire: dict[tuple[str, int | None], float] = {}
        self._hips: dict[int, deque[tuple[float, float, float]]] = {}
        self._seen: dict[int, float] = {}

    def reset(self) -> None:
        self._episodes.clear()
        self._hips.clear()
        self._seen.clear()

    def _check(self, key: tuple[str, int | None], active: bool, t: float, confirm_s: float) -> bool:
        ep = self._episodes.setdefault(key, _Episode())
        if not active:
            if ep.start is not None and t - ep.last_true > self.GRACE_S:
                self._episodes[key] = _Episode()
            return False
        if ep.start is None:
            ep.start = t
        ep.last_true = t
        if ep.fired or t - ep.start < confirm_s:
            return False
        if t - self._last_fire.get(key, -1e9) < self.cfg.alert_cooldown_s:
            return False
        ep.fired = True
        self._last_fire[key] = t
        return True

    def _rapid_drop(self, tid: int, kps: list[list[float]], bbox: list[float] | None,
                    t: float) -> bool:
        vis = self.cfg.visibility_threshold
        if kps[11][2] <= vis or kps[12][2] <= vis:
            return False
        hist = self._hips.setdefault(tid, deque(maxlen=90))
        height = (bbox[3] - bbox[1]) if bbox else 0.0
        hist.append((t, (kps[11][1] + kps[12][1]) / 2, height))
        recent = [h for h in hist if t - h[0] <= self.DROP_WINDOW_S]
        if len(recent) < 2:
            return False
        tallest = max(h[2] for h in recent)
        drop = recent[-1][1] - min(h[1] for h in recent)
        return tallest > 0 and drop > self.DROP_RATIO * tallest

    def _alert(self, kind: str, t: float, track_id: int | None, detail: str,
               **data: Any) -> Alert:
        level, message = MESSAGES[kind]
        return Alert(kind, level, self.source, message, detail, track_id, t, data)

    def update(self, persons: list[dict[str, Any]], quality: dict[str, float] | None,
               t: float) -> list[Alert]:
        cfg, out = self.cfg, []
        for p in persons:
            tid = int(p["id"])
            self._seen[tid] = t
            safety = p.get("safety") or {}
            tech = safety.get("technique", "NONE")
            rapid = self._rapid_drop(tid, p["keypoints"], p.get("bbox"), t)
            fall_s = cfg.fall_confirm_s * (0.5 if rapid else 1.0)
            if self._check(("FALL", tid), tech == "FALL", t, fall_s):
                detail = "Ngã đột ngột" if rapid else "Nằm trên sàn"
                out.append(self._alert("FALL", t, tid, detail, rapid_drop=rapid,
                                       **_metrics(safety)))
            if self._check(("POSTURE", tid), tech == "IMPROPER", t, cfg.posture_confirm_s):
                out.append(self._alert("POSTURE", t, tid, safety.get("detail", ""),
                                       **_metrics(safety)))
        for tid, last in list(self._seen.items()):
            if t - last > self.FORGET_S:
                self._seen.pop(tid, None)
                self._hips.pop(tid, None)
                for kind in ("FALL", "POSTURE"):
                    self._episodes.pop((kind, tid), None)
        if quality is not None:
            low = quality.get("overall", 100.0) < cfg.low_quality_threshold
            if self._check(("CAMERA", None), low, t, cfg.quality_confirm_s):
                out.append(self._alert("CAMERA", t, None,
                                       f"IQA {quality.get('overall', 0):.0f}/100",
                                       iqa=quality.get("overall", 0)))
        return out


def _metrics(safety: dict[str, Any]) -> dict[str, Any]:
    return {k: safety[k] for k in ("spine_deg", "knee_deg", "bbox_ratio") if k in safety}
