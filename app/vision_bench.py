"""Epigraphic vision benchmark: dataset licences, artifact-level splits and model evaluation.

A sign classifier is only trustworthy if it is tested on monuments it never saw in training.
Splitting crops at random leaks the same inscription (same carver, lighting and damage) into
train and test and inflates accuracy, so every split here is made per artifact.

* DATASETS: the public hieroglyph datasets, their licences and whether they may be used.
* load_manifest / manifest_from_folder: items {image, label, artifact, source}.
* artifact_split: deterministic train/val/test by artifact, with a leakage check.
* evaluate_predictions: top-1/top-5, macro recall and F1, per-class recall, expected calibration
  error, unknown-sign rejection AUROC, most confused pairs (pure Python).
* evaluate_onnx: run an ONNX classifier on a split (needs numpy, Pillow, onnxruntime).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

DATASETS: dict[str, dict[str, Any]] = {
    "mmm": {"name": "MMM (Multimodal Multi-script Monumental) hieroglyph crops", "license": "CC BY-SA 4.0",
            "url": "https://github.com/imak-ai-lab/egyptian-hieroglyph-datasets", "annotations": "TLA-derived sign labels",
            "redistributable": True, "benchmark_eligible": True},
    "meh": {"name": "MEH (Middle Egyptian Hieroglyphs) crops", "license": "CC BY-SA 4.0",
            "url": "https://github.com/imak-ai-lab/egyptian-hieroglyph-datasets", "annotations": "Gardiner labels",
            "redistributable": True, "benchmark_eligible": True},
    "mummy": {"name": "MuMMy (Museum Multi-object) images", "license": "CC BY-SA 4.0",
              "url": "https://github.com/imak-ai-lab/egyptian-hieroglyph-datasets", "annotations": "object-level",
              "redistributable": True, "benchmark_eligible": True},
    "franken_unas": {"name": "Franken & van Gemert, Pyramid of Unas glyph dataset (2013)", "license": "not stated",
                     "url": "https://jvgemert.github.io/pub/FrankenACMMM13egyptian.pdf", "annotations": "Gardiner labels, 10 pictures",
                     "redistributable": False, "benchmark_eligible": False,
                     "note": "No licence is stated: use only for private research until permission is obtained."},
    "institutional": {"name": "Institution's own photographs", "license": "set by the institution", "redistributable": False,
                      "benchmark_eligible": True, "note": "Record the rights holder and permission in the manifest's source field."},
}


def dataset_registry() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in DATASETS.items()]


# ------------------------------------------------------------------ manifests
def load_manifest(path: str | Path) -> list[dict[str, Any]]:
    """JSON list or JSONL of {image, label, artifact, source[, bbox]} (label null/"unknown" = out-of-set sign)."""
    text = Path(path).read_text(encoding="utf-8").strip()
    items = json.loads(text) if text.startswith("[") else [json.loads(line) for line in text.splitlines() if line.strip()]
    base = Path(path).resolve().parent
    for item in items:
        for key in ("image", "label", "artifact"):
            if key not in item:
                raise ValueError(f"Manifest item is missing '{key}': {item}")
        if not Path(item["image"]).is_absolute():
            item["image"] = str(base / item["image"])
    return items


def manifest_from_folder(root: str | Path, source: str, artifact_pattern: str = r"^(.*?)[_\-]\d+$") -> list[dict[str, Any]]:
    """ImageFolder layout root/<label>/<file>; the artifact id is taken from the file name (default: text before the last _N)."""
    rx = re.compile(artifact_pattern)
    items = []
    for label_dir in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        for image in sorted(p for p in label_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES):
            m = rx.match(image.stem)
            items.append({"image": str(image), "label": label_dir.name, "artifact": m.group(1) if m else image.stem, "source": source})
    return items


def artifact_split(items: list[dict[str, Any]], ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
                   seed: str = "trans-late") -> dict[str, Any]:
    """Assign whole artifacts to train/val/test by a stable hash, so no monument appears in two splits."""
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise ValueError("ratios must sum to 1")
    splits: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "test": []}
    assignment: dict[str, str] = {}
    for item in items:
        artifact = str(item["artifact"])
        if artifact not in assignment:
            h = int(hashlib.sha256(f"{seed}:{artifact}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
            assignment[artifact] = "train" if h < ratios[0] else "val" if h < ratios[0] + ratios[1] else "test"
        splits[assignment[artifact]].append(item)
    artifacts = {name: {str(i["artifact"]) for i in rows} for name, rows in splits.items()}
    leaks = (artifacts["train"] & artifacts["test"]) | (artifacts["train"] & artifacts["val"]) | (artifacts["val"] & artifacts["test"])
    train_labels = {i["label"] for i in splits["train"]}
    return {"splits": splits, "seed": seed, "ratios": ratios,
            "summary": {name: {"items": len(rows), "artifacts": len(artifacts[name]), "classes": len({i["label"] for i in rows})}
                        for name, rows in splits.items()},
            "leakage": sorted(leaks), "test_classes_unseen_in_train": sorted({i["label"] for i in splits["test"]} - train_labels - {None, "unknown"})}


# ------------------------------------------------------------------ metrics
def _auroc(scores_pos: list[float], scores_neg: list[float]) -> float | None:
    """Probability that a known sign gets a higher confidence than an unknown one (Mann-Whitney)."""
    if not scores_pos or not scores_neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in scores_pos for n in scores_neg)
    return wins / (len(scores_pos) * len(scores_neg))


def evaluate_predictions(rows: Iterable[dict[str, Any]], bins: int = 15) -> dict[str, Any]:
    """rows: {label, ranked: [(label, prob), ...]} -> accuracy, calibration and open-set metrics."""
    rows = list(rows)
    known = [r for r in rows if r["label"] not in (None, "unknown")]
    unknown = [r for r in rows if r["label"] in (None, "unknown")]
    top1 = sum(1 for r in known if r["ranked"] and r["ranked"][0][0] == r["label"])
    top5 = sum(1 for r in known if r["label"] in [label for label, _ in r["ranked"][:5]])
    per_class: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    predicted: Counter = Counter()
    confusions: Counter = Counter()
    calib: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for r in known:
        guess, conf = (r["ranked"][0] if r["ranked"] else (None, 0.0))
        ok = int(guess == r["label"])
        per_class[r["label"]][0] += ok
        per_class[r["label"]][1] += 1
        predicted[guess] += 1
        if not ok and guess is not None:
            confusions[(r["label"], guess)] += 1
        calib[min(bins - 1, int(conf * bins))].append((conf, ok))
    n = len(known) or 1
    recall = {label: hit / total for label, (hit, total) in per_class.items()}
    precision = {label: per_class[label][0] / predicted[label] for label in per_class if predicted[label]}
    f1 = {label: 2 * precision.get(label, 0) * recall[label] / (precision.get(label, 0) + recall[label])
          if precision.get(label, 0) + recall[label] else 0.0 for label in recall}
    ece = sum(len(b) / n * abs(sum(c for c, _ in b) / len(b) - sum(k for _, k in b) / len(b)) for b in calib.values() if b)
    auroc = _auroc([r["ranked"][0][1] for r in known if r["ranked"]], [r["ranked"][0][1] for r in unknown if r["ranked"]])
    return {"items": len(rows), "known_items": len(known), "unknown_items": len(unknown),
            "top1": round(top1 / n, 4), "top5": round(top5 / n, 4),
            "macro_recall": round(sum(recall.values()) / max(1, len(recall)), 4),
            "macro_f1": round(sum(f1.values()) / max(1, len(f1)), 4),
            "expected_calibration_error": round(ece, 4),
            "unknown_rejection_auroc": None if auroc is None else round(auroc, 4),
            "per_class_recall": {k: round(v, 4) for k, v in sorted(recall.items())},
            "most_confused": [{"true": a, "predicted": b, "count": c} for (a, b), c in confusions.most_common(10)]}


# ------------------------------------------------------------------ ONNX
def evaluate_onnx(model_path: str | Path, classes: list[str], items: list[dict[str, Any]], input_size: int | None = None,
                  mean: float = 0.5, std: float = 0.5, grayscale: bool | None = None) -> dict[str, Any]:
    """Run an ONNX image classifier (NCHW input, logits or probabilities output) on manifest items."""
    try:
        import numpy as np
        import onnxruntime as ort
        from PIL import Image
    except ImportError as exc:  # optional dependencies
        raise RuntimeError("Install the vision extras: pip install -r requirements-vision.txt pillow") from exc
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    meta = session.get_inputs()[0]
    shape = meta.shape
    channels = shape[1] if isinstance(shape[1], int) else 3
    size = input_size or (shape[2] if isinstance(shape[2], int) else 224)
    gray = channels == 1 if grayscale is None else grayscale
    rows = []
    for item in items:
        image = Image.open(item["image"]).convert("L" if gray else "RGB").resize((size, size))
        arr = (np.asarray(image, dtype=np.float32) / 255.0 - mean) / std
        arr = arr[None, None, :, :] if gray else arr.transpose(2, 0, 1)[None]
        out = session.run(None, {meta.name: arr.astype(np.float32)})[0][0].astype(np.float64)
        if out.min() < 0 or abs(out.sum() - 1) > 1e-3:  # logits -> softmax
            out = np.exp(out - out.max())
            out = out / out.sum()
        order = np.argsort(-out)[:5]
        rows.append({"label": item["label"], "ranked": [(classes[i], float(out[i])) for i in order]})
    report = evaluate_predictions(rows)
    report["model"] = {"path": str(model_path), "sha256": hashlib.sha256(Path(model_path).read_bytes()).hexdigest(),
                       "input": [channels, size, size], "classes": len(classes)}
    return report


def report_markdown(report: dict[str, Any], title: str = "Vision benchmark") -> str:
    lines = [f"# {title}", "", "| Metric | Value |", "|---|---|"]
    for key in ("items", "top1", "top5", "macro_recall", "macro_f1", "expected_calibration_error", "unknown_rejection_auroc"):
        lines.append(f"| {key.replace('_', ' ')} | {report.get(key)} |")
    if report.get("most_confused"):
        lines += ["", "Most confused: " + ", ".join(f"{c['true']}→{c['predicted']} ({c['count']})" for c in report["most_confused"][:5])]
    return "\n".join(lines) + "\n"


def entropy_bits(probabilities: list[float]) -> float:
    return -sum(p * math.log2(p) for p in probabilities if p > 0)
