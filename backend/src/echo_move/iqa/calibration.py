"""Calibrate / validate IQA overall weights on a controlled degradation dataset.

Ground truth comes from *how much* we degrade a clean image (severity 0–4), not from
human MOS scores. That lets us measure whether a weight vector ranks images in the
right order (Spearman ρ, pairwise accuracy) and search the simplex for better weights.

The default ``(0.25, 0.25, 0.20, 0.15, 0.15)`` = (PIQE, Blur, Contrast, Noise, Exposure)
is always included as a candidate. The report states honestly whether it is optimal
on this dataset, near-optimal, or beaten by another vector.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .metrics import compute_iqa
from .piqe import piqe_full

log = logging.getLogger(__name__)

# Order matches ``compute_iqa``: overall = Σ w_i · metric_i
WEIGHT_NAMES = ("piqe", "blur", "contrast", "noise", "exposure")
# Calibrated by ``make calibrate-iqa`` (F1 @ Overall<40, keep_clean≥0.95).
# Heavier Blur: Laplacian sharpness is the metric that actually falls under blur,
# while PIQE-fast can rise on blurry frames (MSCN variance shrinks).
DEFAULT_WEIGHTS = (0.05, 0.50, 0.20, 0.15, 0.10)
SEVERITY_QUALITY = {0: 100.0, 1: 75.0, 2: 50.0, 3: 25.0, 4: 5.0}


@dataclass(frozen=True)
class Sample:
    path: str
    kind: str          # blur | noise | contrast | exposure_over | exposure_under | mixed | clean
    severity: int      # 0 (clean) … 4 (severe)
    quality: float     # expected overall quality 0–100
    seed: int


@dataclass
class WeightScore:
    weights: tuple[float, float, float, float, float]
    spearman: float
    pairwise: float
    per_kind: dict[str, float]
    mean_kind: float = 0.0
    detect_severe: float = 0.0   # recall: severity≥3 → Overall < threshold
    keep_clean: float = 0.0      # specificity: severity==0 → Overall ≥ threshold
    f1: float = 0.0              # F1 of threshold classifier (bad = severity≥3)
    label: str = ""

    def key(self) -> tuple[float, float, float, float]:
        """Prefer no false alarm on clean, then F1, mean-kind ρ, pairwise.

        ``keep_clean`` is gated: scores with keep_clean < 0.95 sort below safer ones.
        """
        safe = 1.0 if self.keep_clean >= 0.95 else self.keep_clean
        return (safe, self.f1, self.mean_kind, self.pairwise)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "weights": dict(zip(WEIGHT_NAMES, (round(w, 4) for w in self.weights), strict=True)),
            "f1": round(self.f1, 4),
            "detect_severe_rate": round(self.detect_severe, 4),
            "keep_clean_rate": round(self.keep_clean, 4),
            "mean_kind_spearman": round(self.mean_kind, 4),
            "spearman": round(self.spearman, 4),
            "pairwise_accuracy": round(self.pairwise, 4),
            "per_kind_spearman": {k: round(v, 4) for k, v in self.per_kind.items()},
        }


# ------------------------------------------------------------------ scene + degradations
def make_workshop_scene(seed: int, size: tuple[int, int] = (360, 480)) -> np.ndarray:
    """Synthetic industrial scene with edges, texture and a person-like figure."""
    h, w = size
    rng = np.random.default_rng(seed)
    img = np.full((h, w, 3), 118, np.uint8)

    # concrete floor texture
    noise = rng.integers(-28, 29, (h, w), dtype=np.int16)
    for c in range(3):
        ch = img[:, :, c].astype(np.int16) + noise
        img[:, :, c] = np.clip(ch, 0, 255).astype(np.uint8)
    # floor gradient
    for y in range(h // 2, h):
        img[y] = np.clip(img[y].astype(np.int16) - (y - h // 2) // 6, 0, 255).astype(np.uint8)

    # shelves / machines (strong edges for blur metric)
    cv2.rectangle(img, (20, 40), (140, h - 40), (70, 78, 86), -1)
    for y in range(70, h - 50, 45):
        cv2.line(img, (25, y), (135, y), (190, 190, 190), 2)
    cv2.rectangle(img, (w - 150, 50), (w - 30, h - 60), (55, 62, 70), -1)
    cv2.rectangle(img, (w - 145, 90), (w - 35, 200), (40, 140, 200), -1)

    # hazard stripe on floor
    for i in range(0, w, 28):
        cv2.line(img, (i, h - 25), (i + 18, h - 5), (0, 180, 255), 4)

    # worker silhouette
    cx = w // 2 + int(rng.integers(-40, 41))
    cv2.circle(img, (cx, h // 3), 18, (40, 40, 40), -1)                 # head
    cv2.rectangle(img, (cx - 22, h // 3 + 16), (cx + 22, 2 * h // 3), (20, 90, 40), -1)  # torso
    cv2.line(img, (cx - 22, h // 3 + 40), (cx - 55, h // 2 + 20), (40, 40, 40), 8)
    cv2.line(img, (cx + 22, h // 3 + 40), (cx + 55, h // 2 + 20), (40, 40, 40), 8)
    cv2.line(img, (cx - 10, 2 * h // 3), (cx - 18, h - 30), (40, 40, 40), 10)
    cv2.line(img, (cx + 10, 2 * h // 3), (cx + 18, h - 30), (40, 40, 40), 10)

    # overhead lamp highlight
    cv2.circle(img, (w // 2, 20), 40, (220, 220, 200), -1)
    # sharp floor grid → Laplacian energy (do NOT pre-blur; blur is a degradation)
    for x in range(0, w, 40):
        cv2.line(img, (x, h // 2), (x, h), (90, 90, 90), 1)
    for y in range(h // 2, h, 30):
        cv2.line(img, (0, y), (w, y), (90, 90, 90), 1)
    return img


def _to_gray_u8(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr


def degrade(bgr: np.ndarray, kind: str, severity: int, rng: np.random.Generator) -> np.ndarray:
    """Apply a single controlled degradation. severity 0 returns a copy unchanged."""
    out = bgr.copy()
    if severity <= 0:
        return out
    if kind == "blur":
        # ksize 3,7,11,15,21
        k = [0, 3, 7, 11, 15, 21][severity]
        sigma = [0, 0.8, 1.6, 2.5, 3.5, 5.0][severity]
        return cv2.GaussianBlur(out, (k, k), sigma)
    if kind == "noise":
        sigma = [0, 8, 18, 32, 48, 70][severity]
        noise = rng.normal(0, sigma, out.shape)
        return np.clip(out.astype(np.float64) + noise, 0, 255).astype(np.uint8)
    if kind == "contrast":
        # blend toward mean → lower RMS contrast
        factor = [1.0, 0.7, 0.45, 0.25, 0.12, 0.05][severity]
        mean = float(np.mean(out))
        return np.clip(mean + (out.astype(np.float64) - mean) * factor, 0, 255).astype(np.uint8)
    if kind == "exposure_over":
        gain = [1.0, 1.35, 1.7, 2.2, 2.8, 3.5][severity]
        return np.clip(out.astype(np.float64) * gain, 0, 255).astype(np.uint8)
    if kind == "exposure_under":
        gain = [1.0, 0.55, 0.35, 0.2, 0.1, 0.05][severity]
        return np.clip(out.astype(np.float64) * gain, 0, 255).astype(np.uint8)
    if kind == "mixed":
        # equal share of blur + noise + under-exposure (common dirty-lens case)
        out = degrade(out, "blur", max(1, severity - 1), rng)
        out = degrade(out, "noise", max(1, severity - 1), rng)
        out = degrade(out, "exposure_under", severity, rng)
        return out
    raise ValueError(f"unknown degradation kind: {kind}")


# ------------------------------------------------------------------ dataset
KINDS = ("blur", "noise", "contrast", "exposure_over", "exposure_under", "mixed")


def build_dataset(
    out_dir: Path,
    *,
    n_bases: int = 8,
    severities: Sequence[int] = (0, 1, 2, 3, 4),
    seed: int = 0,
    clean_dir: Path | None = None,
) -> list[Sample]:
    """Write PNG samples under ``out_dir`` and return their metadata.

    If ``clean_dir`` contains images, they are used as extra clean bases (real photos).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    bases: list[tuple[str, np.ndarray]] = []
    for i in range(n_bases):
        bases.append((f"synth_{i:02d}", make_workshop_scene(seed + i)))
    if clean_dir and Path(clean_dir).is_dir():
        for p in sorted(Path(clean_dir).iterdir()):
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                continue
            img = cv2.imread(str(p))
            if img is None:
                continue
            h, w = img.shape[:2]
            scale = 480 / max(w, 1)
            if scale < 1:
                img = cv2.resize(img, (int(w * scale), int(h * scale)))
            bases.append((f"real_{p.stem}"[:40], img))

    samples: list[Sample] = []
    for bi, (name, clean) in enumerate(bases):
        for kind in KINDS:
            for sev in severities:
                if sev == 0 and kind != "blur":
                    continue  # one clean copy per base is enough
                img = degrade(clean, kind, sev, rng) if sev else clean
                quality = SEVERITY_QUALITY[sev]
                if kind == "mixed" and sev > 0:
                    quality = max(0.0, quality - 5.0)  # combined damage is slightly worse
                fname = f"{name}__{kind}_s{sev}.png"
                path = out_dir / fname
                cv2.imwrite(str(path), img)
                samples.append(Sample(str(path), "clean" if sev == 0 else kind,
                                      sev, quality, seed + bi))
    meta = out_dir / "manifest.json"
    meta.write_text(json.dumps([asdict(s) for s in samples], indent=2), encoding="utf-8")
    log.info("IQA calibration dataset: %d samples → %s", len(samples), out_dir)
    return samples


def load_manifest(path: Path) -> list[Sample]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Sample(**row) for row in data]


# ------------------------------------------------------------------ scoring
def _spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Spearman rank correlation without SciPy (average ranks for ties)."""
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    def ranks(a: np.ndarray) -> np.ndarray:
        order = a.argsort(kind="mergesort")
        r = np.empty(len(a), float)
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            avg = 0.5 * (i + j) + 1.0
            r[order[i:j + 1]] = avg
            i = j + 1
        return r
    rx, ry = ranks(x), ranks(y)
    return float(np.corrcoef(rx, ry)[0, 1])


def _pairwise_accuracy(scores: Sequence[float], qualities: Sequence[float]) -> float:
    """Fraction of pairs with different GT quality that Overall ranks correctly."""
    s, q = np.asarray(scores, float), np.asarray(qualities, float)
    n, ok, total = len(s), 0, 0
    for i in range(n):
        for j in range(i + 1, n):
            if q[i] == q[j]:
                continue
            total += 1
            # higher quality should get higher overall
            if (q[i] - q[j]) * (s[i] - s[j]) > 0:
                ok += 1
    return ok / total if total else 0.0


def extract_metrics(samples: Sequence[Sample], *, use_full_piqe: bool = False
                    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (N×5 metric matrix, quality vector, kinds)."""
    rows, quals, kinds = [], [], []
    for s in samples:
        img = cv2.imread(s.path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(s.path)
        gray_f = img.astype(np.float64) / 255.0
        r = compute_iqa(img, gray_f)
        piqe = piqe_full(gray_f) if use_full_piqe else r.piqe
        rows.append([piqe, r.blur, r.contrast, r.noise, r.exposure])
        quals.append(s.quality)
        kinds.append(s.kind)
    return np.asarray(rows, float), np.asarray(quals, float), kinds


def overall_from_metrics(metrics: np.ndarray, weights: Sequence[float]) -> np.ndarray:
    w = np.asarray(weights, float)
    w = w / w.sum()
    return metrics @ w


def score_weights(metrics: np.ndarray, qualities: np.ndarray, kinds: Sequence[str],
                  weights: Sequence[float], label: str = "",
                  severe_threshold: float = 40.0) -> WeightScore:
    scores = overall_from_metrics(metrics, weights)
    per: dict[str, float] = {}
    for kind in sorted(set(kinds)):
        idx = [i for i, k in enumerate(kinds) if k == kind]
        if len(idx) >= 3:
            per[kind] = _spearman(scores[idx], qualities[idx])
    kind_vals = [v for k, v in per.items() if k != "clean"]
    mean_kind = float(sum(kind_vals) / len(kind_vals)) if kind_vals else 0.0
    # Operational threshold used by AlertEngine (CAMERA when Overall < 40).
    severe = qualities <= SEVERITY_QUALITY[3]  # severity ≥ 3 → quality ≤ 25
    clean = qualities >= SEVERITY_QUALITY[0]
    predict_bad = scores < severe_threshold
    tp = float(np.sum(predict_bad & severe))
    fp = float(np.sum(predict_bad & ~severe))
    fn = float(np.sum(~predict_bad & severe))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    detect = float(np.mean(predict_bad[severe])) if severe.any() else 0.0
    keep = float(np.mean(~predict_bad[clean])) if clean.any() else 0.0
    w = tuple(float(x) for x in np.asarray(weights) / np.sum(weights))
    return WeightScore(w, _spearman(scores, qualities), _pairwise_accuracy(scores, qualities),
                       per, mean_kind, detect, keep, f1, label)


def _simplex_samples(n: int, rng: np.random.Generator) -> list[tuple[float, ...]]:
    """Random weight vectors on the probability simplex (Dirichlet)."""
    raw = rng.dirichlet(np.ones(5), size=n)
    return [tuple(float(x) for x in row) for row in raw]


def search_weights(
    metrics: np.ndarray,
    qualities: np.ndarray,
    kinds: Sequence[str],
    *,
    n_random: int = 400,
    seed: int = 0,
) -> list[WeightScore]:
    """Score default + baselines + random simplex samples; return ranked list."""
    rng = np.random.default_rng(seed)
    candidates: list[tuple[str, tuple[float, ...]]] = [
        ("default", DEFAULT_WEIGHTS),
        ("equal", (0.2, 0.2, 0.2, 0.2, 0.2)),
        ("piqe_only", (1, 0, 0, 0, 0)),
        ("blur_only", (0, 1, 0, 0, 0)),
        ("contrast_only", (0, 0, 1, 0, 0)),
        ("noise_only", (0, 0, 0, 1, 0)),
        ("exposure_only", (0, 0, 0, 0, 1)),
        ("blur_piqe_heavy", (0.35, 0.35, 0.15, 0.10, 0.05)),
        ("balanced_alt", (0.30, 0.25, 0.20, 0.15, 0.10)),
        ("exposure_heavy", (0.20, 0.20, 0.15, 0.15, 0.30)),
    ]
    for i, w in enumerate(_simplex_samples(n_random, rng)):
        candidates.append((f"rand_{i}", w))

    scored = [score_weights(metrics, qualities, kinds, w, label=name)
              for name, w in candidates]
    scored.sort(key=lambda s: s.key(), reverse=True)
    return scored


def refine_around(metrics: np.ndarray, qualities: np.ndarray, kinds: Sequence[str],
                  centre: Sequence[float], *, n: int = 80, scale: float = 0.08,
                  seed: int = 1) -> WeightScore:
    """Local Gaussian perturbation around a centre weight (renormalised to simplex)."""
    rng = np.random.default_rng(seed)
    best = score_weights(metrics, qualities, kinds, centre, label="local_best")
    c = np.asarray(centre, float)
    for i in range(n):
        trial = np.clip(c + rng.normal(0, scale, size=5), 0.01, None)
        trial = trial / trial.sum()
        sc = score_weights(metrics, qualities, kinds, trial, label=f"local_{i}")
        if sc.key() > best.key():
            best = sc
            best.label = "refined"
    return best


# ------------------------------------------------------------------ report
def verdict(default: WeightScore, best: WeightScore, *, near: float = 0.03) -> str:
    """Compare on operational F1 (Overall < 40 detects severity ≥ 3)."""
    gap = best.f1 - default.f1
    if default.weights == best.weights or gap <= 1e-9:
        return ("DEFAULT_OPTIMAL: trọng số hiện tại đạt F1 cao nhất khi dùng ngưỡng "
                "Overall < 40 để bắt ảnh suy giảm nặng (severity ≥ 3).")
    if gap <= near:
        return (f"DEFAULT_NEAR_OPTIMAL: trọng số hiện tại kém tốt nhất ΔF1={gap:.4f} "
                f"(≤ {near}). Chấp nhận được; không cần đổi.")
    return (f"DEFAULT_SUBOPTIMAL: tìm thấy bộ tốt hơn (ΔF1 = {gap:.4f}). "
            f"Cập nhật Settings.iqa_weights trong config.py rồi chạy lại.")


def run_calibration(
    out_dir: Path,
    *,
    n_bases: int = 8,
    n_random: int = 400,
    use_full_piqe: bool = False,
    clean_dir: Path | None = None,
    seed: int = 0,
) -> dict[str, Any]:
    """End-to-end: build dataset → extract metrics → search → write report JSON + MD."""
    out_dir = Path(out_dir)
    img_dir = out_dir / "images"
    samples = build_dataset(img_dir, n_bases=n_bases, seed=seed, clean_dir=clean_dir)
    metrics, qualities, kinds = extract_metrics(samples, use_full_piqe=use_full_piqe)
    ranked = search_weights(metrics, qualities, kinds, n_random=n_random, seed=seed)
    default = next(s for s in ranked if s.label == "default")
    best_random = ranked[0]
    refined = refine_around(metrics, qualities, kinds, best_random.weights, seed=seed + 1)
    best = refined if refined.key() >= best_random.key() else best_random
    # Keep a stable top-10 including default if it fell off the list.
    top = ranked[:10]
    if not any(s.label == "default" for s in top):
        top = top[:9] + [default]
    report = {
        "n_samples": len(samples),
        "n_bases": n_bases,
        "use_full_piqe": use_full_piqe,
        "weight_order": list(WEIGHT_NAMES),
        "default": default.to_dict(),
        "best": best.to_dict(),
        "top10": [s.to_dict() for s in top],
        "verdict": verdict(default, best),
        "method": {
            "ground_truth": "severity-mapped quality (100,75,50,25,5) on controlled degradations",
            "objective": ("F1 of threshold classifier Overall<40 vs severity≥3, then "
                          "keep-clean rate, mean per-kind Spearman, pairwise accuracy"),
            "search": f"{n_random} Dirichlet samples + baselines + local refine",
            "caveat": ("Tối ưu theo mục tiêu vận hành của ECHO MOVE (cảnh báo CAMERA khi "
                       "Overall < 40), trên dataset suy giảm có kiểm soát — không phải "
                       "MOS người xem trên toàn bộ ảnh hiện trường."),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    (out_dir / "report.md").write_text(markdown_report(report), encoding="utf-8")
    np.savez(out_dir / "metrics.npz", metrics=metrics, qualities=qualities,
             kinds=np.array(kinds))
    return report


def markdown_report(report: dict[str, Any]) -> str:
    d, b = report["default"], report["best"]
    lines = [
        "# IQA weight calibration report",
        "",
        f"**Verdict:** {report['verdict']}",
        "",
        f"- Samples: **{report['n_samples']}** (bases={report['n_bases']})",
        f"- PIQE mode: `{'full' if report['use_full_piqe'] else 'fast'}`",
        f"- Weight order: `{', '.join(report['weight_order'])}`",
        "",
        "## Default vs best",
        "",
        "| | Weights | F1 | Detect sev≥3 | Keep clean | Mean-kind ρ |",
        "|---|---|---:|---:|---:|---:|",
        (f"| Default | `{_fmt_w(d['weights'])}` | {d['f1']:.4f} | "
         f"{d['detect_severe_rate']:.4f} | {d['keep_clean_rate']:.4f} | "
         f"{d['mean_kind_spearman']:.4f} |"),
        (f"| Best | `{_fmt_w(b['weights'])}` | {b['f1']:.4f} | "
         f"{b['detect_severe_rate']:.4f} | {b['keep_clean_rate']:.4f} | "
         f"{b['mean_kind_spearman']:.4f} |"),
        "",
        "### Per-degradation Spearman (default)",
        "",
    ]
    for k, v in d.get("per_kind_spearman", {}).items():
        lines.append(f"- `{k}`: {v:.4f}")
    lines += [
        "",
        "### Per-degradation Spearman (best)",
        "",
    ]
    for k, v in b.get("per_kind_spearman", {}).items():
        lines.append(f"- `{k}`: {v:.4f}")
    lines += [
        "",
        "## Top 10 candidates",
        "",
        "| Rank | Label | F1 | Detect | Keep clean | Mean-kind ρ | Weights |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for i, s in enumerate(report["top10"], 1):
        lines.append(
            f"| {i} | {s['label']} | {s['f1']:.4f} | {s['detect_severe_rate']:.4f} | "
            f"{s['keep_clean_rate']:.4f} | {s['mean_kind_spearman']:.4f} | "
            f"`{_fmt_w(s['weights'])}` |"
        )
    lines += [
        "",
        "## Method",
        "",
        f"- Ground truth: {report['method']['ground_truth']}",
        f"- Objective: {report['method']['objective']}",
        f"- Search: {report['method']['search']}",
        f"- Caveat: {report['method']['caveat']}",
        "",
        "## Apply best weights",
        "",
        "Ghi vào `backend/src/echo_move/config.py`:",
        "",
        "```python",
        f"iqa_weights = {_tuple_w(b['weights'])}",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def _fmt_w(w: dict[str, float] | Iterable[float]) -> str:
    if isinstance(w, dict):
        return ", ".join(f"{w[n]:.3f}" for n in WEIGHT_NAMES)
    return ", ".join(f"{float(x):.3f}" for x in w)


def _tuple_w(w: dict[str, float]) -> str:
    return "(" + ", ".join(f"{w[n]:.2f}" for n in WEIGHT_NAMES) + ")"
