#!/usr/bin/env python3
"""Build a controlled IQA degradation dataset and search for optimal Overall weights.

Usage:
    make calibrate-iqa
    python scripts/calibrate_iqa.py --bases 8 --random 400
    python scripts/calibrate_iqa.py --clean-dir data/iqa_clean   # optional real photos

Writes ``output/iqa_calib/report.md`` + ``report.json`` + sample PNGs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from echo_move.iqa.calibration import DEFAULT_WEIGHTS, run_calibration  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "iqa_calib")
    ap.add_argument("--bases", type=int, default=8, help="number of synthetic clean scenes")
    ap.add_argument("--random", type=int, default=400, help="Dirichlet weight samples")
    ap.add_argument("--full-piqe", action="store_true", help="use block-wise PIQE (slower)")
    ap.add_argument("--clean-dir", type=Path, default=None,
                    help="optional folder of real clean photos mixed into the dataset")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    report = run_calibration(
        args.out,
        n_bases=args.bases,
        n_random=args.random,
        use_full_piqe=args.full_piqe,
        clean_dir=args.clean_dir,
        seed=args.seed,
    )
    print(report["verdict"])
    d, b = report["default"], report["best"]
    print(f"default F1={d['f1']:.4f}  detect={d['detect_severe_rate']:.4f}  "
          f"keep_clean={d['keep_clean_rate']:.4f}  mean-kind ρ={d['mean_kind_spearman']:.4f}")
    print(f"best    F1={b['f1']:.4f}  detect={b['detect_severe_rate']:.4f}  "
          f"keep_clean={b['keep_clean_rate']:.4f}  mean-kind ρ={b['mean_kind_spearman']:.4f}")
    names = ("piqe", "blur", "contrast", "noise", "exposure")
    best_w = tuple(b["weights"][k] for k in names)
    print(f"default weights {DEFAULT_WEIGHTS}")
    print(f"best     weights {best_w}")
    print(f"report → {args.out / 'report.md'}")


if __name__ == "__main__":
    main()
