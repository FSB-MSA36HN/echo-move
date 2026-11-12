"""Track-dependent fall signal: body collapsed relative to the worker's own standing height.

A fall towards / away from the camera foreshortens the torso, so the "lying" geometry in
``classifier`` misses it; the body box still shrinks sharply compared with how tall the same
track was while standing. The standing baseline is learned per track (upright frames only)
and the hips must also have moved down, so walking away from the camera (smaller but hips
rise towards the horizon) does not count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .classifier import FALL_RESULT, is_fall

UPRIGHT_SPINE_DEG = 20.0
HIP_DROP_RATIO = 0.2  # hips at least this × standing height below their standing level


@dataclass
class _Baseline:
    height: float = 0.0
    hip_y: float = 0.0
    samples: int = 0
    last_t: float = 0.0


class FallAnalyzer:
    MIN_SAMPLES = 5
    FORGET_S = 10.0

    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self._base: dict[int, _Baseline] = {}

    def reset(self) -> None:
        self._base.clear()

    def refine(self, track_id: int, safety: dict[str, Any], t: float) -> dict[str, Any]:
        """Learn the standing baseline and upgrade ``safety`` to FALL when collapsed."""
        for tid in [k for k, b in self._base.items() if t - b.last_t > self.FORGET_S]:
            self._base.pop(tid, None)
        signals = safety.get("signals")
        if not signals or not self.cfg.fall_multisignal:
            return safety
        height, hip_y = float(safety.get("height", 0.0)), float(safety.get("hip_y", 0.0))
        b = self._base.setdefault(track_id, _Baseline())
        b.last_t = t
        ready = b.samples >= self.MIN_SAMPLES
        upright = (safety.get("technique") == "NONE"
                   and safety.get("spine_deg", 90.0) < UPRIGHT_SPINE_DEG and height > 0
                   and (not ready or height > 0.8 * b.height))
        if upright:
            a = 0.2 if b.samples >= self.MIN_SAMPLES else 1.0 / (b.samples + 1)
            b.height += a * (height - b.height)
            b.hip_y += a * (hip_y - b.hip_y)
            b.samples += 1
            return safety
        if not ready or safety.get("technique") == "FALL":
            return safety
        collapsed = (height < self.cfg.fall_collapse_ratio * b.height
                     and hip_y - b.hip_y > HIP_DROP_RATIO * b.height)
        if not collapsed:
            return safety
        out = {**safety, "signals": {**signals, "collapsed": True}}
        legs_bent = safety.get("knee_deg", 180.0) < self.cfg.knee_bent_deg
        if signals.get("lying") or not legs_bent:
            if is_fall(bool(signals.get("lying")), signals.get("head_low"), True, self.cfg):
                level, color, label = FALL_RESULT
                out.update(level=level, color=color, label=label, technique="FALL",
                           detail=f"Đổ người (cao {height / b.height:.0%} lúc đứng)")
        return out
