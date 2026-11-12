"""Offline evaluation of the fall rules on public datasets (UR Fall, Le2i, any labelled folder).

Two stages so rule variants can be compared without re-running the detector:

1. ``extract``  — run YOLOv8-Pose on every sampled frame, keep raw keypoints (cacheable JSON);
2. ``replay``   — tracker → classifier → fall analyzer → alert engine on those keypoints.

Scoring is per video: a positive video is detected when a FALL/MANDOWN alert lands inside the
annotated fall window (± tolerance), or anywhere when the dataset has no frame annotation.
Every FALL alert on a negative (ADL) video, or outside the window, is a false alarm.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from .alerts.engine import AlertEngine
from .config import Settings
from .pose.classifier import classify_posture
from .pose.fall import FallAnalyzer
from .pose.tracker import PoseTracker

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}
FALL_TYPES = ("FALL", "MANDOWN")


@dataclass
class VideoCase:
    path: str
    positive: bool
    fall_start_s: float | None = None
    fall_end_s: float | None = None


@dataclass
class Extraction:
    fps: float  # sampling rate actually used
    aspect: float  # width / height
    duration_s: float
    frames: list[tuple[float, list[list[list[float]]]]] = field(default_factory=list)


@dataclass
class CaseResult:
    path: str
    positive: bool
    detected: bool
    false_alarms: int
    latency_s: float | None
    duration_s: float
    alerts: list[tuple[str, float]]


# ---------------------------------------------------------------------- datasets
def _videos(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in VIDEO_EXT)


def discover(dataset: str, root: str | Path, labels: str | None = None) -> list[VideoCase]:
    """``urfd``: fall-XX-cam0.mp4 / adl-XX-cam0.mp4 (video-level labels).
    ``le2i``: <scene>/Videos/video (N).avi + Annotation_files/video (N).txt (frame window).
    ``folder``: name containing "fall" is positive, or a CSV ``name,label[,start_s,end_s]``."""
    root = Path(root)
    if dataset == "urfd":
        return [VideoCase(str(p), p.name.lower().startswith("fall")) for p in _videos(root)
                if re.match(r"(fall|adl)-\d+", p.name.lower())]
    if dataset == "le2i":
        cases = []
        for p in _videos(root):
            ann = p.parent.parent / "Annotation_files" / (p.stem + ".txt")
            if not ann.is_file():
                ann = p.parent.parent / "Annotations_files" / (p.stem + ".txt")
            start, end = parse_le2i_annotation(ann) if ann.is_file() else (None, None)
            fps = 25.0
            positive = start is not None and end is not None and end > start
            cases.append(VideoCase(str(p), positive,
                                   start / fps if positive and start is not None else None,
                                   end / fps if positive and end is not None else None))
        return cases
    if labels:
        out = []
        with open(labels, encoding="utf-8") as f:
            for row in csv.reader(f):
                if not row or row[0].startswith("#") or row[0] == "name":
                    continue
                fall_start = float(row[2]) if len(row) > 2 and row[2] else None
                fall_end = float(row[3]) if len(row) > 3 and row[3] else None
                out.append(VideoCase(str(root / row[0]), row[1].strip() in ("1", "fall", "true"),
                                     fall_start, fall_end))
        return out
    return [VideoCase(str(p), "fall" in p.name.lower()) for p in _videos(root)]


def parse_le2i_annotation(path: Path) -> tuple[int | None, int | None]:
    lines = [ln.strip() for ln in path.read_text(errors="ignore").splitlines() if ln.strip()]
    try:
        return int(float(lines[0])), int(float(lines[1]))
    except (IndexError, ValueError):
        return None, None


# ---------------------------------------------------------------------- stages
def extract(path: str, detector: Any, fps: float = 10.0) -> Extraction:
    import cv2

    cap = cv2.VideoCapture(path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(src_fps / fps))
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 4
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 3
    ex = Extraction(fps=src_fps / step, aspect=w / h, duration_s=0.0)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            dets, _ = detector.detect_raw(frame)
            ex.frames.append((i / src_fps, dets))
        i += 1
    cap.release()
    ex.duration_s = i / src_fps
    return ex


def replay(ex: Extraction, cfg: Settings) -> list[tuple[str, float]]:
    tracker, fall, engine = PoseTracker(), FallAnalyzer(cfg), AlertEngine(cfg, "eval")
    alerts: list[tuple[str, float]] = []
    for t, dets in ex.frames:
        persons = [
            {"id": tp.track_id, "keypoints": tp.keypoints, "bbox": list(tp.bbox),
             "safety": fall.refine(tp.track_id,
                                   classify_posture(tp.keypoints, cfg, ex.aspect), t)}
            for tp in tracker.update(dets, t)
        ]
        alerts += [(a.type, a.t) for a in engine.update(persons, None, t)]
    return alerts


def score(case: VideoCase, alerts: Iterable[tuple[str, float]], duration_s: float,
          tolerance_s: float = 2.0, mandown_s: float = 10.0) -> CaseResult:
    falls = [(k, t) for k, t in alerts if k in FALL_TYPES]
    hits: list[float] = []
    false_alarms = 0
    for kind, t in falls:
        if not case.positive:
            false_alarms += kind == "FALL"
            continue
        if case.fall_start_s is None:
            hits.append(t)
            continue
        end = (case.fall_end_s or case.fall_start_s) + tolerance_s + mandown_s
        if case.fall_start_s - tolerance_s <= t <= end:
            hits.append(t)
        elif kind == "FALL":
            false_alarms += 1
    latency = None
    if hits and case.fall_start_s is not None:
        latency = max(0.0, min(hits) - case.fall_start_s)
    return CaseResult(case.path, case.positive, bool(hits), false_alarms, latency, duration_s,
                      list(alerts))


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    pos = [r for r in results if r.positive]
    neg = [r for r in results if not r.positive]
    tp = sum(r.detected for r in pos)
    fn = len(pos) - tp
    fp_videos = sum(r.false_alarms > 0 for r in neg)
    tn = len(neg) - fp_videos
    precision = tp / (tp + fp_videos) if tp + fp_videos else 0.0
    recall = tp / len(pos) if pos else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    lat = [r.latency_s for r in pos if r.latency_s is not None]
    neg_hours = sum(r.duration_s for r in neg) / 3600
    false_total = sum(r.false_alarms for r in results)
    return {
        "videos": len(results), "positives": len(pos), "negatives": len(neg),
        "tp": tp, "fn": fn, "fp_videos": fp_videos, "tn": tn,
        "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
        "specificity": round(tn / len(neg), 3) if neg else None,
        "latency_mean_s": round(statistics.mean(lat), 2) if lat else None,
        "latency_median_s": round(statistics.median(lat), 2) if lat else None,
        "false_alarms": false_total,
        "false_alarms_per_hour_adl": round(sum(r.false_alarms for r in neg) / neg_hours, 1)
        if neg_hours else None,
    }


def evaluate(cases: list[VideoCase], extractions: dict[str, Extraction],
             cfg: Settings) -> tuple[dict[str, Any], list[CaseResult]]:
    results = []
    for case in cases:
        ex = extractions.get(case.path)
        if ex is None:
            continue
        results.append(score(case, replay(ex, cfg), ex.duration_s,
                             mandown_s=cfg.mandown_s))
    return summarize(results), results


def variants(cfg: Settings) -> dict[str, Settings]:
    return {"multi-signal": replace(cfg, fall_multisignal=True),
            "legacy": replace(cfg, fall_multisignal=False)}


# ---------------------------------------------------------------------- cache
def save_extraction(ex: Extraction, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(ex)), encoding="utf-8")


def load_extraction(path: Path) -> Extraction:
    d = json.loads(path.read_text(encoding="utf-8"))
    return Extraction(d["fps"], d["aspect"], d["duration_s"],
                      [(float(t), dets) for t, dets in d["frames"]])


def markdown(table: dict[str, dict[str, Any]]) -> str:
    cols = ["videos", "tp", "fn", "fp_videos", "tn", "precision", "recall", "f1",
            "specificity", "latency_mean_s", "false_alarms_per_hour_adl"]
    lines = ["| Luật | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for name, s in table.items():
        lines.append(f"| {name} | " + " | ".join("-" if s.get(c) is None else str(s[c])
                                                 for c in cols) + " |")
    return "\n".join(lines)
