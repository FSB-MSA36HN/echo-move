"""Multi-person tracker in the spirit of ByteTrack (Zhang et al., 2022), on pose boxes.

* Each track predicts its box with a constant-velocity model, so a worker falling or
  walking fast still overlaps their predicted box.
* Detections are split by mean keypoint confidence: confident ones are matched first;
  weak ones (occluded, half visible) are only used to *continue* existing tracks, which
  keeps IDs through partial occlusion instead of spawning new ones.
* Matching is greedy on IoU, with a centre-distance fallback gated by the track's size.

Ultralytics' built-in ``model.track`` keeps its state inside the shared model, which would
mix IDs across cameras; this tracker lives in each stream's pipeline instead.
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


def detection_score(kps: list[Keypoint]) -> float:
    return sum(k[2] for k in kps) / len(kps) if kps else 0.0


@dataclass
class Track:
    id: int
    bbox: BBox
    last_t: float
    hits: int = 0
    vx: float = 0.0  # box-centre velocity (normalised units / s)
    vy: float = 0.0
    smoother: KeypointSmoother = field(default_factory=KeypointSmoother)

    def predict(self, t: float) -> BBox:
        dt = min(max(t - self.last_t, 0.0), 0.5)
        dx, dy = self.vx * dt, self.vy * dt
        b = self.bbox
        return b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy

    def diag(self) -> float:
        return math.hypot(self.bbox[2] - self.bbox[0], self.bbox[3] - self.bbox[1])


@dataclass
class TrackedPerson:
    track_id: int
    keypoints: list[Keypoint]
    bbox: BBox


class PoseTracker:
    HIGH_SCORE = 0.5  # first-stage detections
    MIN_NEW_SCORE = 0.2  # weaker detections never start a track
    SIZE_GATE = 0.6  # centre distance allowed as a fraction of the track's box diagonal

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

    def _match(self, dets: list[int], boxes: list[BBox | None], tracks: set[int],
               t: float) -> dict[int, int]:
        candidates: list[tuple[float, int, int]] = []
        for di in dets:
            box = boxes[di]
            if box is None:
                continue
            for tid in tracks:
                tr = self.tracks[tid]
                pred = tr.predict(t)
                score = max(iou(box, pred), iou(box, tr.bbox))
                if score < self.iou_threshold:
                    (cx, cy), (tx, ty) = _centre(box), _centre(pred)
                    gate = max(self.max_centre_dist, self.SIZE_GATE * tr.diag())
                    dist = math.hypot(cx - tx, cy - ty)
                    if dist > gate:
                        continue
                    score = self.iou_threshold * (1 - dist / gate) * 0.99
                candidates.append((score, di, tid))
        candidates.sort(reverse=True)
        assigned: dict[int, int] = {}
        used: set[int] = set()
        for _, di, tid in candidates:
            if di in assigned or tid in used:
                continue
            assigned[di] = tid
            used.add(tid)
        return assigned

    def update(self, detections: list[list[Keypoint]], t: float) -> list[TrackedPerson]:
        self.tracks = {i: tr for i, tr in self.tracks.items() if t - tr.last_t <= self.max_age_s}
        boxes = [keypoint_bbox(d) for d in detections]
        scores = [detection_score(d) for d in detections]
        high = [i for i, s in enumerate(scores) if s >= self.HIGH_SCORE]
        low = [i for i, s in enumerate(scores) if s < self.HIGH_SCORE]

        assigned = self._match(high, boxes, set(self.tracks), t)
        free = set(self.tracks) - set(assigned.values())
        assigned.update(self._match(low, boxes, free, t))

        out: list[TrackedPerson] = []
        for di, (kps, box) in enumerate(zip(detections, boxes, strict=True)):
            if box is None:
                continue
            if di in assigned:
                tr = self.tracks[assigned[di]]
                dt = t - tr.last_t
                if dt > 0:
                    (cx, cy), (px, py) = _centre(box), _centre(tr.bbox)
                    a = 0.5 if tr.hits > 1 else 1.0
                    tr.vx += a * ((cx - px) / dt - tr.vx)
                    tr.vy += a * ((cy - py) / dt - tr.vy)
            else:
                if scores[di] < self.MIN_NEW_SCORE:
                    continue
                tr = Track(self._next_id, box, t)
                self._next_id += 1
                self.tracks[tr.id] = tr
            tr.bbox, tr.last_t = box, t
            tr.hits += 1
            out.append(TrackedPerson(tr.id, tr.smoother.apply(kps, t), box))
        return out
