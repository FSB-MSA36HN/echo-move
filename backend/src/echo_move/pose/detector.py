"""YOLOv8-Pose + MediaPipe Hands wrapper. Heavy imports are optional.

The detector is stateless per stream (tracking/smoothing live in ``pipeline``) and is
shared by the browser WebSocket and every server-side camera, so inference is serialised
with a lock: Ultralytics predictors are not thread-safe.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import cv2
import numpy as np

from ..config import Settings

log = logging.getLogger(__name__)


class PoseDetector:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.model: Any = None
        self.hands: Any = None
        self._half = False
        self._lock = threading.Lock()
        self._load()

    @property
    def available(self) -> bool:
        return self.model is not None

    def _load(self) -> None:
        if self.cfg.demo_mode:
            log.warning("DEMO_MODE enabled — models not loaded")
            return
        try:
            import torch
            from ultralytics import YOLO
        except ImportError:
            log.warning("ultralytics/torch not installed → DEMO mode")
            return
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._half = device == "cuda"
            log.info("Loading %s on %s", self.cfg.model_name, device)
            self.model = YOLO(self.cfg.model_name).to(device)
        except Exception:
            log.exception("YOLO failed to load → DEMO mode")
            self.model = None
            return
        try:
            import mediapipe as mp

            self.hands = mp.solutions.hands.Hands(
                static_image_mode=False, max_num_hands=2,
                min_detection_confidence=0.3, min_tracking_confidence=0.3,
                model_complexity=0,
            )
        except Exception:
            log.warning("MediaPipe Hands unavailable — hand tracking disabled")

    def detect_raw(self, frame_bgr: np.ndarray) -> tuple[list[list[list[float]]], list[Any]]:
        """Return (raw keypoints per person, hands) for one BGR frame. Coordinates are 0-1."""
        if self.model is None:
            return [], []
        people: list[list[list[float]]] = []
        with self._lock:
            res = self.model(frame_bgr, verbose=False, conf=self.cfg.yolo_conf, half=self._half)
            hands_res = (self.hands.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
                         if self.hands is not None else None)
        if res and res[0].keypoints is not None:
            xyn = res[0].keypoints.xyn.cpu().numpy()
            conf = res[0].keypoints.conf
            conf_np = (conf.cpu().numpy() if conf is not None
                       else np.ones(xyn.shape[:2], dtype=np.float32))
            kps_all = np.concatenate([xyn, conf_np[..., None]], axis=-1)
            people = [kps_all[i].tolist() for i in range(min(len(kps_all), self.cfg.max_persons))]
        hands: list[Any] = []
        if hands_res is not None:
            for hd in hands_res.multi_hand_landmarks or []:
                hands.append([{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hd.landmark])
        return people, hands
