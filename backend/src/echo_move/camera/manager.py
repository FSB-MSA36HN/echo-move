"""Builds camera workers from ``ECHO_CAMERAS`` / ``ECHO_CAMERAS_FILE``."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..alerts import AlertHub
from ..config import Settings
from ..pipeline import StreamPipeline
from ..pose.detector import PoseDetector
from .worker import CameraWorker, CaptureFactory, Source

log = logging.getLogger(__name__)


def _coerce(source: Any) -> Source:
    if isinstance(source, int):
        return source
    s = str(source).strip()
    return int(s) if s.isdigit() else s


def parse_cameras(spec: str = "", file: str = "") -> dict[str, Source]:
    """``"kho=rtsp://u:p@10.0.0.5/stream1,cong=0"`` and/or a JSON file
    (``{"kho": "rtsp://..."}`` or ``[{"id": "kho", "source": "rtsp://..."}]``)."""
    cams: dict[str, Source] = {}
    if file:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
        items = data.items() if isinstance(data, dict) else ((d["id"], d["source"]) for d in data)
        for cid, src in items:
            cams[str(cid)] = _coerce(src)
    for i, part in enumerate(p.strip() for p in spec.split(",") if p.strip()):
        cid, sep, src = part.partition("=")
        if not sep or "/" in cid or ":" in cid:
            cid, src = f"cam{i + 1}", part
        cams[cid.strip()] = _coerce(src)
    return cams


class CameraManager:
    def __init__(self, cfg: Settings, detector: PoseDetector, hub: AlertHub | None,
                 capture_factory: CaptureFactory | None = None,
                 sources: dict[str, Source] | None = None):
        if sources is None:
            try:
                sources = parse_cameras(cfg.cameras, cfg.cameras_file)
            except (OSError, ValueError, KeyError) as exc:
                log.error("invalid camera configuration: %s", exc)
                sources = {}
        self.workers = {
            cid: CameraWorker(cid, src, StreamPipeline(cid, detector, cfg, hub), cfg,
                              capture_factory)
            for cid, src in sources.items()
        }

    def start(self) -> None:
        for w in self.workers.values():
            w.start()

    def stop(self) -> None:
        for w in self.workers.values():
            w.stop()

    def get(self, cam_id: str) -> CameraWorker | None:
        return self.workers.get(cam_id)

    def statuses(self) -> list[dict[str, Any]]:
        return [w.status() for w in self.workers.values()]
