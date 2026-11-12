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
from ..zones import CameraOptions, OptionsStore, load_file_options, parse_options
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
                 sources: dict[str, Source] | None = None,
                 options_store: OptionsStore | None = None):
        file_opts: dict[str, dict[str, Any]] = {}
        if sources is None:
            try:
                sources = parse_cameras(cfg.cameras, cfg.cameras_file)
                file_opts = load_file_options(cfg.cameras_file)
            except (OSError, ValueError, KeyError) as exc:
                log.error("invalid camera configuration: %s", exc)
                sources = {}
        self.options_store = options_store or OptionsStore(None)
        overrides = self.options_store.load()
        self.workers: dict[str, CameraWorker] = {}
        for cid, src in sources.items():
            pipe = StreamPipeline(cid, detector, cfg, hub)
            raw = overrides.get(cid, file_opts.get(cid))
            try:
                pipe.configure(parse_options(raw, cfg.zone_dwell_s))
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                log.error("camera %s: invalid zones/rules (%s) — ignored", cid, exc)
            self.workers[cid] = CameraWorker(cid, src, pipe, cfg, capture_factory)

    def start(self) -> None:
        for w in self.workers.values():
            w.start()

    def stop(self) -> None:
        for w in self.workers.values():
            w.stop()

    def get(self, cam_id: str) -> CameraWorker | None:
        return self.workers.get(cam_id)

    def configure(self, cam_id: str, options: CameraOptions) -> bool:
        w = self.workers.get(cam_id)
        if w is None:
            return False
        w.pipeline.configure(options)
        self.options_store.save(cam_id, options)
        return True

    def statuses(self) -> list[dict[str, Any]]:
        return [w.status() for w in self.workers.values()]
