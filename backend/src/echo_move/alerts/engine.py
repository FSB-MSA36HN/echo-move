"""Temporal alert confirmation.

The per-frame classifier is noisy (occlusion, motion blur, a worker crouching for a second),
so an alert is raised only when a condition persists:

* FALL      — classifier says FALL for ``fall_confirm_s`` (halved after a rapid hip drop).
* MANDOWN   — still lying ``mandown_s`` after the fall was confirmed (did not get up).
* RECOVERED — a worker whose fall was reported is upright again for ``recover_s``.
* POSTURE   — improper bending (IMPROPER) for ``posture_confirm_s``.
* ERGO      — cumulative time at REBA ≥ ``ergo_reba_high`` within ``ergo_window_s``.
* ZONE      — feet inside a configured danger zone for the zone's dwell time.
* PPE       — required protective equipment missing for ``ppe_confirm_s``.
* CAMERA    — overall IQA below ``low_quality_threshold`` for ``quality_confirm_s``.

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
    "MANDOWN": ("CRITICAL", "Công nhân không đứng dậy sau ngã"),
    "RECOVERED": ("INFO", "Công nhân đã đứng dậy sau ngã"),
    "POSTURE": ("WARNING", "Cúi sai tư thế kéo dài"),
    "ERGO": ("WARNING", "Tư thế có hại tích lũy (REBA cao)"),
    "ZONE": ("WARNING", "Xâm nhập vùng nguy hiểm"),
    "PPE": ("WARNING", "Thiếu đồ bảo hộ"),
    "CAMERA": ("WARNING", "Chất lượng camera kém / bị che"),
    "OFFLINE": ("WARNING", "Camera mất tín hiệu"),
}
ALERT_TYPES = tuple(MESSAGES)
PPE_LABELS = {"helmet": "mũ bảo hộ", "vest": "áo phản quang"}
LYING = "FALL"
UPRIGHT = ("NONE", "PROPER_LIFT", "PARTIAL")


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
    motion: float = 0.0  # EMA of body-normalised keypoint speed (body heights / s)
    fallen: bool = False  # a FALL / MANDOWN was reported and the worker has not got up
    ergo: deque[tuple[float, float]] = field(default_factory=deque)


class AlertEngine:
    GRACE_S = 0.5
    MANDOWN_GRACE_S = 2.0  # a lying worker's classification flickers more
    FORGET_S = 5.0
    DROP_WINDOW_S = 1.5
    DROP_RATIO = 0.25  # hip falls by > 25 % of body height within DROP_WINDOW_S
    STILL_SPEED = 0.05  # below this the worker counts as motionless

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
        cfg, out = self.cfg, []
        for p in persons:
            tid = int(p["id"])
            prev_t = self._seen.get(tid)
            self._seen[tid] = t
            tr = self._tracks.setdefault(tid, _Track())
            safety = p.get("safety") or {}
            tech = safety.get("technique", "NONE")
            rapid = self._rapid_drop(tid, p["keypoints"], p.get("bbox"), t)
            motion = self._motion(tr, p["keypoints"], p.get("bbox"), t)
            fall_s = cfg.fall_confirm_s * (0.5 if rapid else 1.0)
            if self._check(("FALL", tid), tech == LYING, t, fall_s):
                detail = "Ngã đột ngột" if rapid else "Nằm trên sàn"
                out.append(self._alert("FALL", t, tid, detail, rapid_drop=rapid,
                                       **_metrics(safety)))
                tr.fallen = True
            if self._check(("MANDOWN", tid), tech == LYING, t, fall_s + cfg.mandown_s,
                           grace_s=self.MANDOWN_GRACE_S):
                still = motion < self.STILL_SPEED
                lying_s = cfg.mandown_s + fall_s
                detail = (f"Nằm bất động {lying_s:.0f} s" if still
                          else f"Nằm {lying_s:.0f} s, còn cử động")
                out.append(self._alert("MANDOWN", t, tid, detail, motionless=still,
                                       motion=round(motion, 3), **_metrics(safety)))
                tr.fallen = True
            if self._check(("RECOVERED", tid), tr.fallen and tech in UPRIGHT, t,
                           cfg.recover_s, cooldown_s=0):
                out.append(self._alert("RECOVERED", t, tid, "Đã đứng dậy"))
                tr.fallen = False
                self._episodes.pop(("RECOVERED", tid), None)
            if self._check(("POSTURE", tid), tech == "IMPROPER", t, cfg.posture_confirm_s):
                out.append(self._alert("POSTURE", t, tid, safety.get("detail", ""),
                                       **_metrics(safety)))
            out += self._ergo(tid, tr, safety, t, prev_t)
            for zone in p.get("zones") or []:
                name = zone["name"] if isinstance(zone, dict) else str(zone)
                dwell = zone.get("dwell_s", cfg.zone_dwell_s) if isinstance(zone, dict) \
                    else cfg.zone_dwell_s
                if self._check(("ZONE", (name, tid)), True, t, dwell):
                    out.append(self._alert("ZONE", t, tid, f"Vùng: {name}", zone=name))
            self._idle_zones(tid, {z["name"] if isinstance(z, dict) else str(z)
                                   for z in p.get("zones") or []}, t)
            missing = [k for k, v in (p.get("ppe") or {}).items()
                       if v is False and k in cfg.ppe_required]
            if self._check(("PPE", tid), bool(missing), t, cfg.ppe_confirm_s):
                names = ", ".join(PPE_LABELS.get(k, k) for k in missing)
                out.append(self._alert("PPE", t, tid, f"Thiếu {names}", missing=missing))
        for tid, last in list(self._seen.items()):
            if t - last > self.FORGET_S:
                self._seen.pop(tid, None)
                self._hips.pop(tid, None)
                self._tracks.pop(tid, None)
                for key in [k for k in self._episodes if _track_of(k) == tid]:
                    self._episodes.pop(key, None)
        if quality is not None:
            low = quality.get("overall", 100.0) < cfg.low_quality_threshold
            if self._check(("CAMERA", None), low, t, cfg.quality_confirm_s):
                out.append(self._alert("CAMERA", t, None,
                                       f"IQA {quality.get('overall', 0):.0f}/100",
                                       iqa=quality.get("overall", 0)))
        return [a for a in out if a.type not in self.disabled]

    def _ergo(self, tid: int, tr: _Track, safety: dict[str, Any], t: float,
              prev_t: float | None) -> list[Alert]:
        cfg = self.cfg
        reba = safety.get("reba")
        if reba is not None and reba >= cfg.ergo_reba_high and prev_t is not None:
            tr.ergo.append((t, min(t - prev_t, 1.0)))
        while tr.ergo and t - tr.ergo[0][0] > cfg.ergo_window_s:
            tr.ergo.popleft()
        exposure = sum(dt for _, dt in tr.ergo)
        key = ("ERGO", tid)
        if exposure < cfg.ergo_exposure_s:
            return []
        if t - self._last_fire.get(key, -1e9) < cfg.ergo_window_s:
            return []
        self._last_fire[key] = t
        mins = cfg.ergo_window_s / 60
        return [self._alert("ERGO", t, tid,
                            f"REBA ≥ {cfg.ergo_reba_high} trong {exposure:.0f} s / {mins:.0f} phút",
                            reba=reba, exposure_s=round(exposure, 1))]

    def _idle_zones(self, tid: int, inside: set[str], t: float) -> None:
        for key in [k for k in self._episodes if k[0] == "ZONE" and k[1][1] == tid
                    and k[1][0] not in inside]:
            self._check(key, False, t, 0)


def _track_of(key: tuple[str, Any]) -> Any:
    sub = key[1]
    return sub[1] if isinstance(sub, tuple) else sub


def _metrics(safety: dict[str, Any]) -> dict[str, Any]:
    return {k: safety[k] for k in ("spine_deg", "knee_deg", "bbox_ratio", "reba")
            if k in safety}
