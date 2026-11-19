"""Temporal alert confirmation for the five posture events.

Action events (snapshot + notify + optional clip) need a sustained pose:

* FALL   — ``fall_confirm_s`` (halved after a rapid hip drop);
* STOOP / SQUAT — ``posture_confirm_s``.

Log-only events fire immediately (confirm 0) and skip image/clip/notify:

* STANDING — cooldown still applies to avoid spam.

PARTIAL is a detection state only (bbox overlay) — it never raises an alert.

Short dropouts (< ``GRACE_S``) do not reset an episode. Each (type, track) pair fires at
most once per ``alert_cooldown_s``.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from ..config import Settings

MESSAGES = {
    "FALL": ("CRITICAL", "Phát hiện công nhân bị ngã"),
    "STANDING": ("INFO", "Công nhân đang đứng"),
    "SQUAT": ("INFO", "Công nhân ngồi xổm"),
    "STOOP": ("WARNING", "Công nhân cúi khom lưng"),
    "PARTIAL": ("WARNING", "Một phần của người"),  # kept for API/legacy rows; not emitted
}
ALERT_TYPES = tuple(MESSAGES)
# Full handling (confirm + snapshot + notify/clip). Everything else is log-only.
ACTION_TYPES = frozenset({"FALL", "SQUAT", "STOOP"})
LOG_ONLY_TYPES = frozenset({"STANDING"})
LYING = "FALL"


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


@dataclass
class _Track:
    last_kps: list[list[float]] | None = None
    last_t: float = 0.0
    motion: float = 0.0


class AlertEngine:
    GRACE_S = 0.5
    FORGET_S = 5.0
    DROP_WINDOW_S = 1.5
    DROP_RATIO = 0.25

    def __init__(self, cfg: Settings, source: str):
        self.cfg = cfg
        self.source = source
        self.disabled: set[str] = set()
        self._episodes: dict[tuple[str, Any], _Episode] = {}
        self._last_fire: dict[tuple[str, Any], float] = {}
        self._hips: dict[int, deque[tuple[float, float, float]]] = {}
        self._tracks: dict[int, _Track] = {}
        self._seen: dict[int, float] = {}

    def reset(self) -> None:
        self._episodes.clear()
        self._hips.clear()
        self._tracks.clear()
        self._seen.clear()

    def _check(self, key: tuple[str, Any], active: bool, t: float, confirm_s: float,
               grace_s: float | None = None, cooldown_s: float | None = None) -> bool:
        ep = self._episodes.setdefault(key, _Episode())
        if not active:
            if ep.start is not None and t - ep.last_true > (grace_s or self.GRACE_S):
                self._episodes[key] = _Episode()
            return False
        if ep.start is None:
            ep.start = t
        ep.last_true = t
        if ep.fired or t - ep.start < confirm_s:
            return False
        cooldown = self.cfg.alert_cooldown_s if cooldown_s is None else cooldown_s
        if t - self._last_fire.get(key, -1e9) < cooldown:
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

    def _motion(self, tr: _Track, kps: list[list[float]], bbox: list[float] | None,
                t: float) -> float:
        vis = self.cfg.visibility_threshold
        if tr.last_kps is not None and t > tr.last_t:
            moved = [math.hypot(a[0] - b[0], a[1] - b[1])
                     for a, b in zip(kps, tr.last_kps, strict=False)
                     if a[2] > vis and b[2] > vis]
            if moved:
                size = max((bbox[3] - bbox[1], bbox[2] - bbox[0]) if bbox else (0.0,))
                speed = sum(moved) / len(moved) / max(size, 0.05) / (t - tr.last_t)
                tr.motion = 0.7 * tr.motion + 0.3 * min(speed, 5.0)
        tr.last_kps, tr.last_t = [list(k) for k in kps], t
        return tr.motion

    def _alert(self, kind: str, t: float, track_id: int | None, detail: str,
               **data: Any) -> Alert:
        level, message = MESSAGES[kind]
        return Alert(kind, level, self.source, message, detail, track_id, t, data)

    def update(self, persons: list[dict[str, Any]], quality: dict[str, float] | None,
               t: float) -> list[Alert]:
        del quality  # IQA no longer raises CAMERA events
        cfg, out = self.cfg, []
        for p in persons:
            tid = int(p["id"])
            self._seen[tid] = t
            tr = self._tracks.setdefault(tid, _Track())
            safety = p.get("safety") or {}
            tech = safety.get("technique", "STANDING")
            rapid = self._rapid_drop(tid, p["keypoints"], p.get("bbox"), t)
            self._motion(tr, p["keypoints"], p.get("bbox"), t)
            fall_s = cfg.fall_confirm_s * (0.5 if rapid else 1.0)
            if self._check(("FALL", tid), tech == LYING, t, fall_s):
                detail = "Ngã đột ngột" if rapid else "Nằm trên sàn"
                out.append(self._alert("FALL", t, tid, detail, rapid_drop=rapid,
                                       **_metrics(safety)))
            if self._check(("STOOP", tid), tech == "STOOP", t, cfg.posture_confirm_s):
                out.append(self._alert("STOOP", t, tid, safety.get("detail", ""),
                                       **_metrics(safety)))
            if self._check(("SQUAT", tid), tech == "SQUAT", t, cfg.posture_confirm_s):
                out.append(self._alert("SQUAT", t, tid, safety.get("detail", ""),
                                       **_metrics(safety)))
            # PARTIAL: no alert — incomplete person is overlay-only.
            # STANDING: log immediately (confirm_s=0), still cooldown-limited.
            if self._check(("STANDING", tid), tech == "STANDING", t, 0.0):
                out.append(self._alert("STANDING", t, tid, safety.get("detail", ""),
                                       **_metrics(safety)))
        for tid, last in list(self._seen.items()):
            if t - last > self.FORGET_S:
                self._seen.pop(tid, None)
                self._hips.pop(tid, None)
                self._tracks.pop(tid, None)
                for key in [k for k in self._episodes if _track_of(k) == tid]:
                    self._episodes.pop(key, None)
        return [a for a in out if a.type not in self.disabled]


def _track_of(key: tuple[str, Any]) -> Any:
    sub = key[1]
    return sub[1] if isinstance(sub, tuple) else sub


def _metrics(safety: dict[str, Any]) -> dict[str, Any]:
    return {k: safety[k] for k in ("spine_deg", "knee_deg", "bbox_ratio", "reba")
            if k in safety}
