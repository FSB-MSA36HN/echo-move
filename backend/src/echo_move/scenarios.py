"""Synthetic demo scenarios (single source of truth, shared with the web UI).

The JSON lives in ``data/scenarios.json``; ``scripts/export_scenarios.py`` copies it
to ``web/data/scenarios.json`` so both tiers stay in sync.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def load_scenarios() -> dict[str, dict[str, Any]]:
    text = resources.files("echo_move").joinpath("data/scenarios.json").read_text("utf-8")
    return json.loads(text)


class DemoGenerator:
    """Cycles through the scenarios every ``seconds_per_scenario`` seconds."""

    def __init__(self, fps: int, seconds_per_scenario: int = 4):
        self._scenarios = load_scenarios()
        self._order = list(self._scenarios)
        self._fps = fps
        self._period = fps * seconds_per_scenario
        self._frame = 0
        self._index = 0

    def next_frame(self, matlab_iqa: dict[str, Any] | None) -> dict[str, Any]:
        self._frame += 1
        if self._frame % self._period == 0:
            self._index = (self._index + 1) % len(self._order)
        sc = self._scenarios[self._order[self._index]]
        breath = math.sin(self._frame / self._fps * 2) * 0.008
        kps = [
            [x, y - breath, c] if 5 <= i <= 12 and c >= 0.25 else [x, y, c]
            for i, (x, y, c) in enumerate(sc["kps"])
        ]
        detected = any(k[2] > 0.25 for k in kps)
        return {
            "detected": detected,
            "persons": [{"id": 0, "keypoints": kps, "safety": sc["safety"]}] if detected else [],
            "hands": [],
            "quality": sc["iqa"],
            "env_hazards": sc["env"],
            "matlab_iqa": matlab_iqa,
            "mode": "DEMO",
            "version": "20.0",
        }
