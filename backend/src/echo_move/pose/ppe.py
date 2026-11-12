"""PPE (helmet / hi-vis vest) detections assigned to tracked people.

The detector itself is any YOLO *detection* model trained on a PPE dataset (``PPE_MODEL``),
e.g. Roboflow "Construction Site Safety" (Hardhat, NO-Hardhat, Safety Vest, NO-Safety Vest)
or "Hard Hat Workers" (helmet, head). Class names are normalised by ``normalize_label``.

Each detection box is matched to the person whose head region (helmet) or torso region (vest)
covers most of it. A positive class sets the item to True, a negative class to False; when the
region is visible but nothing was detected the item is False, when the region is not visible
it is None (unknown, never alerts). ``ppe_confirm_s`` in the alert engine absorbs flicker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

Box = tuple[float, float, float, float]

POSITIVE = {"hardhat": "helmet", "helmet": "helmet", "safetyhelmet": "helmet",
            "vest": "vest", "safetyvest": "vest", "reflectivevest": "vest", "hivis": "vest",
            "hivisvest": "vest", "reflectivejacket": "vest"}
NEGATIVE = {"nohardhat": "helmet", "nohelmet": "helmet", "head": "helmet",
            "withouthelmet": "helmet", "novest": "vest", "nosafetyvest": "vest",
            "withoutvest": "vest"}
MIN_OVERLAP = 0.3


@dataclass(frozen=True)
class PPEDetection:
    item: str
    present: bool
    conf: float
    box: Box  # normalised x1, y1, x2, y2


def normalize_label(name: str) -> tuple[str, bool] | None:
    key = re.sub(r"[^a-z]", "", name.lower())
    if key in POSITIVE:
        return POSITIVE[key], True
    if key in NEGATIVE:
        return NEGATIVE[key], False
    return None


def _visible(kps: list[list[float]], idx: range | tuple[int, ...], vis: float) -> list[list[float]]:
    return [kps[i] for i in idx if i < len(kps) and kps[i][2] >= vis]


def regions(kps: list[list[float]], vis: float) -> dict[str, Box | None]:
    """Head box (helmet) and torso box (vest) from COCO-17 keypoints."""
    shoulders = _visible(kps, (5, 6), vis)
    hips = _visible(kps, (11, 12), vis)
    head = _visible(kps, range(5), vis)
    width = abs(shoulders[0][0] - shoulders[1][0]) if len(shoulders) == 2 else 0.0
    out: dict[str, Box | None] = {"helmet": None, "vest": None}
    if head or shoulders:
        if head:
            cx = sum(p[0] for p in head) / len(head)
            cy = min(p[1] for p in head)
        else:
            cx = sum(p[0] for p in shoulders) / len(shoulders)
            cy = min(p[1] for p in shoulders) - width * 0.8
        r = max(width * 0.6, 0.03)
        out["helmet"] = (cx - r, cy - r * 1.4, cx + r, cy + r * 0.8)
    if len(shoulders) == 2 and hips:
        xs = [p[0] for p in shoulders + hips]
        ys = [p[1] for p in shoulders + hips]
        pad = width * 0.15
        out["vest"] = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys))
    return out


def _coverage(det: Box, region: Box) -> float:
    """Fraction of the detection box that lies inside the region."""
    w = min(det[2], region[2]) - max(det[0], region[0])
    h = min(det[3], region[3]) - max(det[1], region[1])
    area = (det[2] - det[0]) * (det[3] - det[1])
    return w * h / area if w > 0 and h > 0 and area > 0 else 0.0


def assign_ppe(persons: list[list[list[float]]], detections: list[PPEDetection],
               vis: float) -> list[dict[str, bool | None]]:
    """Per person ``{"helmet": bool|None, "vest": bool|None}``."""
    regs = [regions(kps, vis) for kps in persons]
    found: list[dict[str, list[bool]]] = [{"helmet": [], "vest": []} for _ in persons]
    for det in sorted(detections, key=lambda d: -d.conf):
        best, best_cov = -1, MIN_OVERLAP
        for i, reg in enumerate(regs):
            region = reg.get(det.item)
            if region is not None and (cov := _coverage(det.box, region)) >= best_cov:
                best, best_cov = i, cov
        if best >= 0:
            found[best][det.item].append(det.present)
    out = []
    for reg, hits in zip(regs, found, strict=True):
        status: dict[str, bool | None] = {}
        for item in ("helmet", "vest"):
            if reg[item] is None:
                status[item] = None
            else:
                status[item] = any(hits[item])  # one positive wins over negatives / absence
        out.append(status)
    return out


def parse_results(result: Any) -> list[PPEDetection]:
    """Ultralytics detection result → normalised PPE detections."""
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []
    names = getattr(result, "names", {}) or {}
    xyxyn = boxes.xyxyn.cpu().numpy()
    cls = boxes.cls.cpu().numpy().astype(int)
    conf = boxes.conf.cpu().numpy()
    out = []
    for box, c, p in zip(xyxyn, cls, conf, strict=True):
        label = normalize_label(str(names.get(int(c), c)))
        if label is not None:
            out.append(PPEDetection(label[0], label[1], float(p),
                                    (float(box[0]), float(box[1]), float(box[2]), float(box[3]))))
    return out
