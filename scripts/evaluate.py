"""Evaluate the fall rules (multi-signal vs. legacy) on a public fall dataset.

Usage:
  python scripts/evaluate.py urfd  data/urfd        # fall-XX-cam0.mp4 / adl-XX-cam0.mp4
  python scripts/evaluate.py le2i  data/le2i        # <scene>/Videos + Annotation_files
  python scripts/evaluate.py folder data/clips [--labels labels.csv]

Keypoints are cached in output/eval_cache/<dataset>/ so re-scoring after a rule change
takes seconds. Requires the AI extras (make install-ai) for the first run.
Results: printed as a Markdown table and written to output/eval_<dataset>.json.
"""

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from echo_move.config import Settings
from echo_move.evaluation import (
    discover,
    evaluate,
    extract,
    load_extraction,
    markdown,
    save_extraction,
    variants,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("dataset", choices=["urfd", "le2i", "folder"])
    ap.add_argument("root")
    ap.add_argument("--labels", help="CSV name,label[,start_s,end_s] for 'folder'")
    ap.add_argument("--fps", type=float, default=10.0, help="analysed frames per second")
    ap.add_argument("--limit", type=int, default=0, help="only the first N videos")
    ap.add_argument("--cache", default=str(ROOT / "output" / "eval_cache"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    cases = discover(a.dataset, a.root, a.labels)
    if a.limit:
        cases = cases[: a.limit]
    if not cases:
        print(f"Không tìm thấy video trong {a.root}", file=sys.stderr)
        return 1
    cfg = replace(Settings(), demo_mode=False)
    cache = Path(a.cache) / a.dataset
    detector = None
    extractions = {}
    for i, case in enumerate(cases, 1):
        key = hashlib.sha1(f"{Path(case.path).resolve()}|{a.fps}".encode()).hexdigest()[:16]
        path = cache / f"{Path(case.path).stem}_{key}.json"
        if path.is_file():
            extractions[case.path] = load_extraction(path)
            continue
        if detector is None:
            from echo_move.pose.detector import PoseDetector

            detector = PoseDetector(cfg)
            if not detector.available:
                print("YOLOv8-Pose chưa cài (make install-ai).", file=sys.stderr)
                return 2
        t0 = time.time()
        ex = extract(case.path, detector, a.fps)
        save_extraction(ex, path)
        extractions[case.path] = ex
        print(f"[{i}/{len(cases)}] {Path(case.path).name}: {len(ex.frames)} frame "
              f"({time.time() - t0:.1f}s)", file=sys.stderr)

    table, details = {}, {}
    for name, vcfg in variants(cfg).items():
        summary, results = evaluate(cases, extractions, vcfg)
        table[name] = summary
        details[name] = [asdict(r) for r in results]
    print(markdown(table))
    out = Path(a.out) if a.out else ROOT / "output" / f"eval_{a.dataset}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"dataset": a.dataset, "fps": a.fps, "summary": table,
                               "videos": details}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"\n→ {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
