"""YOLOv8-Pose + MediaPipe Hands wrapper. Heavy imports are optional."""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from ..config import Settings
from .classifier import classify_posture
from .filters import KeypointSmoother

log = logging.getLogger(__name__)


class PoseDetector:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.model: Any = None
        self.hands: Any = None
        self._half = False
        self._smoothers = [KeypointSmoother() for _ in range(cfg.max_persons)]
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

    def reset(self) -> None:
        for s in self._smoothers:
            s.reset()

    def detect(self, frame_bgr: np.ndarray, t: float) -> tuple[list[dict[str, Any]], list[Any]]:
        """Return (persons, hands) for one BGR frame."""
        persons: list[dict[str, Any]] = []
        res = self.model(frame_bgr, verbose=False, conf=self.cfg.yolo_conf, half=self._half)
        if res and res[0].keypoints is not None:
            # Normalised (0-1) xy so the web UI and the classifier share one coordinate space.
            xyn = res[0].keypoints.xyn.cpu().numpy()
            conf = res[0].keypoints.conf
            conf_np = (conf.cpu().numpy() if conf is not None
                       else np.ones(xyn.shape[:2], dtype=np.float32))
            kps_all = np.concatenate([xyn, conf_np[..., None]], axis=-1)
            for i in range(min(len(kps_all), self.cfg.max_persons)):
                kps = self._smoothers[i].apply(kps_all[i].tolist(), t)
                persons.append({"id": i, "keypoints": kps,
                                "safety": classify_posture(kps, self.cfg)})
        hands: list[Any] = []
        if self.hands is not None:
            result = self.hands.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
            for hd in result.multi_hand_landmarks or []:
                hands.append([{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hd.landmark])
        return persons, hands
