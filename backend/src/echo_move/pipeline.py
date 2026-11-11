"""Per-stream processing shared by the browser WebSocket and server-side cameras.

detector (shared) → tracker → classifier → IQA → alert engine → hub (store/notify/push)
"""

from __future__ import annotations

import base64
import time
from collections import deque
from typing import Any

import cv2
import numpy as np

from . import __version__
from .alerts import AlertEngine, AlertHub
from .config import Settings
from .iqa import compute_iqa
from .pose.classifier import classify_posture
from .pose.detector import PoseDetector
from .pose.tracker import PoseTracker
from .render import annotate, encode_jpeg

SAFE_ENV: dict[str, Any] = {"hazards": [], "overall_level": "SAFE", "overall_color": [0, 1, 0]}


def env_from_quality(iqa: dict[str, float], cfg: Settings) -> dict[str, Any]:
    if iqa["overall"] < cfg.low_quality_threshold:
        return {"hazards": [{"name": "LOW_Q", "label": "ẢNH KÉM", "advice": "Kiểm tra camera"}],
                "overall_level": "RISK", "overall_color": [1, 0.65, 0]}
    return SAFE_ENV


def decode_frame(data_url: str, max_width: int) -> np.ndarray | None:
    try:
        payload = data_url.split(",", 1)[-1]
        frame = cv2.imdecode(np.frombuffer(base64.b64decode(payload), np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    if frame is None:
        return None
    return resize_max_width(frame, max_width)


def resize_max_width(frame: np.ndarray, max_width: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)))
    return frame


class StreamPipeline:
    def __init__(self, source: str, detector: PoseDetector, cfg: Settings,
                 hub: AlertHub | None = None):
        self.source = source
        self.detector = detector
        self.cfg = cfg
        self.hub = hub
        self.tracker = PoseTracker()
        self.engine = AlertEngine(cfg, source)
        self.frames = 0
        self._bench: deque[float] = deque(maxlen=100)

    def reset(self) -> None:
        self.tracker.reset()
        self.engine.reset()

    def process(self, frame: np.ndarray, t: float | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        t = time.time() if t is None else t
        h, w = frame.shape[:2]
        raw, hands = self.detector.detect_raw(frame)
        persons = [
            {"id": tp.track_id, "keypoints": tp.keypoints, "bbox": list(tp.bbox),
             "safety": classify_posture(tp.keypoints, self.cfg, w / h)}
            for tp in self.tracker.update(raw, t)
        ]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        iqa = compute_iqa(
            gray, gray.astype(np.float64) / 255.0, mode=self.cfg.piqe_mode,
            weights=self.cfg.iqa_weights,
            compute_full=self.frames % self.cfg.piqe_sample_every == 0,
        ).to_dict()
        alerts = self.engine.update(persons, iqa, t)
        events = [self._publish(a, frame, persons) for a in alerts]
        frame_ms = (time.perf_counter() - started) * 1000
        self._bench.append(frame_ms)
        avg = sum(self._bench) / len(self._bench)
        self.frames += 1
        return {
            "detected": bool(persons), "persons": persons, "hands": hands,
            "quality": iqa, "env_hazards": env_from_quality(iqa, self.cfg),
            "alerts": events, "source": self.source, "frame": {"w": w, "h": h},
            "benchmark": {"frame_ms": round(frame_ms, 2), "avg_frame_ms": round(avg, 2),
                          "fps_actual": round(1000.0 / max(avg, 1), 1),
                          "frames_total": self.frames},
            "mode": "AI" if self.detector.available else "IQA", "version": __version__,
        }

    def observe(self, payload: dict[str, Any], t: float | None = None) -> dict[str, Any]:
        """Run alert rules on an externally produced payload (demo generator)."""
        t = time.time() if t is None else t
        alerts = self.engine.update(payload.get("persons", []), payload.get("quality"), t)
        payload["alerts"] = [self._publish(a, None, payload.get("persons", [])) for a in alerts]
        return payload

    def _publish(self, alert: Any, frame: np.ndarray | None,
                 persons: list[dict[str, Any]]) -> dict[str, Any]:
        if self.hub is None:
            return dict(alert.to_dict())
        jpeg = None
        if frame is not None:
            img = annotate(frame, persons, title=f"{self.source} - {alert.type}",
                           highlight=alert.track_id, vis=self.cfg.visibility_threshold)
            jpeg = encode_jpeg(img)
        return self.hub.publish(alert, jpeg)
