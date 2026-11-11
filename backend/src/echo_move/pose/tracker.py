"""Lightweight multi-person tracker (greedy IoU + centre distance, SORT-style without Kalman).

Gives each worker a stable ``track_id`` so smoothing and temporal alert rules follow the
same person across frames instead of the detector's per-frame ordering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .filters import Keypoint, KeypointSmoother

BBox = tuple[float, float, float, float]


def keypoint_bbox(kps: list[Keypoint], vis: float = 0.25) -> BBox | None:
    pts = [(k[0], k[1]) for k in kps if k[2] > vis]
    if len(pts) < 2:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def iou(a: BBox, b: BBox) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _centre(b: BBox) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


@dataclass
class Track:
    id: int
    bbox: BBox
    last_t: float
    hits: int = 0
    smoother: KeypointSmoother = field(default_factory=KeypointSmoother)


@dataclass
class TrackedPerson:
    track_id: int
    keypoints: list[Keypoint]
    bbox: BBox


class PoseTracker:
    def __init__(self, iou_threshold: float = 0.2, max_centre_dist: float = 0.12,
                 max_age_s: float = 1.5):
        self.iou_threshold = iou_threshold
        self.max_centre_dist = max_centre_dist
        self.max_age_s = max_age_s
        self.tracks: dict[int, Track] = {}
        self._next_id = 1

    def reset(self) -> None:
        self.tracks.clear()
        self._next_id = 1

    def update(self, detections: list[list[Keypoint]], t: float) -> list[TrackedPerson]:
        self.tracks = {i: tr for i, tr in self.tracks.items() if t - tr.last_t <= self.max_age_s}
        boxes = [keypoint_bbox(d) for d in detections]

        candidates: list[tuple[float, int, int]] = []
        for di, box in enumerate(boxes):
            if box is None:
                continue
            for tid, tr in self.tracks.items():
                score = iou(box, tr.bbox)
                if score < self.iou_threshold:
                    (cx, cy), (tx, ty) = _centre(box), _centre(tr.bbox)
                    dist = math.hypot(cx - tx, cy - ty)
                    if dist > self.max_centre_dist:
                        continue
                    score = self.iou_threshold * (1 - dist / self.max_centre_dist) * 0.99
                candidates.append((score, di, tid))
        candidates.sort(reverse=True)

        assigned: dict[int, int] = {}
        used_tracks: set[int] = set()
        for _, di, tid in candidates:
            if di in assigned or tid in used_tracks:
                continue
            assigned[di] = tid
            used_tracks.add(tid)

        out: list[TrackedPerson] = []
        for di, (kps, box) in enumerate(zip(detections, boxes, strict=True)):
            if box is None:
                continue
            if di in assigned:
                tid = assigned[di]
            else:
                tid = self._next_id
                self._next_id += 1
                self.tracks[tid] = Track(tid, box, t)
            tr = self.tracks[tid]
            tr.bbox, tr.last_t = box, t
            tr.hits += 1
            out.append(TrackedPerson(tid, tr.smoother.apply(kps, t), box))
        return out
