"""Pose/IQA fixtures for unit tests (scenarios.json).

Provides known keypoints (stand/bend/fall) so pytest can exercise classifier and
alert rules without loading YOLO.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any


@lru_cache(maxsize=1)
def load_scenarios() -> dict[str, dict[str, Any]]:
    text = resources.files("echo_move").joinpath("data/scenarios.json").read_text("utf-8")
    return json.loads(text)
