"""Per-camera danger zones and rule switches.

Configured in ``ECHO_CAMERAS_FILE`` (or edited from the web UI, saved to
``<data_dir>/camera_config.json``)::

    [{"id": "kho", "source": "rtsp://...",
      "zones": [{"name": "Máy dập", "points": [[0.1, 0.6], [0.4, 0.6], [0.4, 1], [0.1, 1]],
                 "dwell_s": 1}],
      "disabled_rules": ["POSTURE"]}]

Points are normalised (x / width, y / height). A worker is inside a zone when the point
between the ankles (or the bottom-centre of the body box) lies in the polygon.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

Point = tuple[float, float]


@dataclass
class Zone:
    name: str
    points: list[Point]
    dwell_s: float = 1.0

    def contains(self, p: Point) -> bool:
        return point_in_polygon(p, self.points)


@dataclass
class CameraOptions:
    zones: list[Zone] = field(default_factory=list)
    disabled_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"zones": [asdict(z) for z in self.zones],
                "disabled_rules": list(self.disabled_rules)}


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1:
            inside = not inside
    return inside


def foot_point(kps: list[list[float]], bbox: list[float] | None, vis: float) -> Point | None:
    ankles = [kps[i] for i in (15, 16) if len(kps) > i and kps[i][2] > vis]
    if ankles:
        return (sum(a[0] for a in ankles) / len(ankles), max(a[1] for a in ankles))
    if bbox:
        return ((bbox[0] + bbox[2]) / 2, bbox[3])
    return None


def parse_options(data: dict[str, Any] | None, default_dwell: float = 1.0) -> CameraOptions:
    """Validate one camera's options (raises ValueError on malformed zones)."""
    data = data or {}
    zones = []
    for i, z in enumerate(data.get("zones") or []):
        pts = [(float(p[0]), float(p[1])) for p in z.get("points", [])]
        if len(pts) < 3:
            raise ValueError(f"zone {i}: needs at least 3 points")
        if not all(-0.01 <= c <= 1.01 for pt in pts for c in pt):
            raise ValueError(f"zone {i}: points must be normalised to 0..1")
        zones.append(Zone(str(z.get("name") or f"Vùng {i + 1}")[:40], pts,
                          float(z.get("dwell_s", default_dwell))))
    rules = [str(r).upper() for r in data.get("disabled_rules") or []]
    return CameraOptions(zones, rules)


def load_file_options(file: str) -> dict[str, dict[str, Any]]:
    """Extra per-camera keys from the ECHO_CAMERAS_FILE list format."""
    if not file:
        return {}
    data = json.loads(Path(file).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return {}
    return {str(d["id"]): {k: d[k] for k in ("zones", "disabled_rules") if k in d}
            for d in data if isinstance(d, dict) and "id" in d}


class OptionsStore:
    """Runtime overrides saved from the UI (``<data_dir>/camera_config.json``)."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, dict[str, Any]]:
        if self.path is None or not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            log.error("cannot read %s: %s", self.path, exc)
            return {}

    def save(self, cam_id: str, options: CameraOptions) -> None:
        if self.path is None:
            return
        with self._lock:
            data = self.load()
            data[cam_id] = options.to_dict()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
