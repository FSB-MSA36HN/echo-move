"""One thread pair per camera: a reader that always keeps only the newest frame (no RTSP
backlog / growing latency) and a processor that runs the pipeline at ``camera_fps``.
Lost streams are reopened with exponential backoff (1 s → 30 s).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

from ..config import Settings
from ..pipeline import StreamPipeline, resize_max_width
from ..render import annotate, encode_jpeg

log = logging.getLogger(__name__)

Source = str | int
CaptureFactory = Callable[[Source], Any]

NETWORK_PREFIXES = ("rtsp://", "rtsps://", "rtmp://", "http://", "https://", "udp://", "tcp://")


def is_file_source(source: Source) -> bool:
    return isinstance(source, str) and not source.lower().startswith(NETWORK_PREFIXES)


def mask_source(source: Source) -> str:
    """Hide credentials (rtsp://user:pass@host → rtsp://***@host)."""
    return re.sub(r"//[^/@]+@", "//***@", str(source))


def _open_capture(source: Source) -> Any:
    cap = cv2.VideoCapture(source)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass
    return cap


class CameraWorker:
    MAX_BACKOFF_S = 30.0
    STALE_S = 5.0

    def __init__(self, cam_id: str, source: Source, pipeline: StreamPipeline, cfg: Settings,
                 capture_factory: CaptureFactory | None = None):
        self.id = cam_id
        self.source = source
        self.pipeline = pipeline
        self.cfg = cfg
        self._factory = capture_factory or _open_capture
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_t = 0.0
        self._seq = 0
        self._threads: list[threading.Thread] = []
        self.state = "idle"
        self.error: str | None = None
        self.reconnects = 0
        self.fps = 0.0
        self.latest: dict[str, Any] | None = None
        self.latest_jpeg: bytes | None = None
        self.result_seq = 0

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        self.state = "connecting"
        for name, fn in (("reader", self._reader), ("processor", self._processor)):
            th = threading.Thread(target=fn, name=f"cam-{self.id}-{name}", daemon=True)
            th.start()
            self._threads.append(th)

    def stop(self) -> None:
        self._stop.set()
        for th in self._threads:
            th.join(timeout=5)
        self._threads.clear()
        self.state = "stopped"

    # ------------------------------------------------------------------ threads
    def _reader(self) -> None:
        backoff = 1.0
        file_src = is_file_source(self.source)
        while not self._stop.is_set():
            cap = self._factory(self.source)
            if cap is None or not cap.isOpened():
                self.state, self.error = "reconnecting", "cannot open source"
                self.reconnects += 1
                log.warning("camera %s: cannot open %s, retry in %.0fs", self.id,
                            mask_source(self.source), backoff)
                if cap is not None:
                    cap.release()
                self._stop.wait(backoff)
                backoff = min(backoff * 2, self.MAX_BACKOFF_S)
                continue
            backoff = 1.0
            self.state, self.error = "online", None
            log.info("camera %s online (%s)", self.id, mask_source(self.source))
            delay = 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 25.0) if file_src else 0.0
            rewinds = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    if file_src and rewinds < 3:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        rewinds += 1
                        continue
                    break
                rewinds = 0
                with self._lock:
                    self._frame, self._frame_t = frame, time.time()
                    self._seq += 1
                if delay:
                    self._stop.wait(delay)
            cap.release()
            if not self._stop.is_set():
                self.state, self.error = "reconnecting", "stream lost"
                self.reconnects += 1
                log.warning("camera %s: stream lost, reconnecting", self.id)
                self._stop.wait(backoff)

    def _processor(self) -> None:
        period = 1.0 / max(self.cfg.camera_fps, 0.5)
        last_seq, count, tick = -1, 0, time.time()
        while not self._stop.wait(period):
            with self._lock:
                frame, seq, ft = self._frame, self._seq, self._frame_t
            if frame is None or seq == last_seq:
                if self.state == "online" and ft and time.time() - ft > self.STALE_S:
                    self.state = "stalled"
                continue
            last_seq = seq
            try:
                frame = resize_max_width(frame, self.cfg.max_frame_width)
                result = self.pipeline.process(frame, ft)
                result["camera"] = self.id
                img = annotate(frame, result["persons"], title=self.id,
                               vis=self.cfg.visibility_threshold)
                self.latest, self.latest_jpeg = result, encode_jpeg(img, 75)
                self.result_seq += 1
                if self.state == "stalled":
                    self.state = "online"
            except Exception as exc:
                self.error = f"processing: {exc}"
                log.exception("camera %s processing failed", self.id)
            count += 1
            now = time.time()
            if now - tick >= 1.0:
                self.fps, count, tick = count / (now - tick), 0, now

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        latest = self.latest or {}
        return {
            "id": self.id, "source": mask_source(self.source), "state": self.state,
            "error": self.error, "fps": round(self.fps, 1), "reconnects": self.reconnects,
            "persons": len(latest.get("persons", [])),
            "quality": (latest.get("quality") or {}).get("overall"),
            "last_frame_age_s": round(time.time() - self._frame_t, 1) if self._frame_t else None,
        }
