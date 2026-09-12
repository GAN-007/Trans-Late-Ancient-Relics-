from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from dataclasses import dataclass, asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .epigraphy import CORE_SIGNS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = PROJECT_ROOT / "models" / "relic_detector.onnx"
DEFAULT_CLASSES = PROJECT_ROOT / "models" / "classes.json"


@dataclass
class LocalVisionConfig:
    enabled: bool
    available: bool
    model_path: str
    classes_path: str
    model_exists: bool
    classes_exists: bool
    dependencies: dict[str, bool]
    providers: list[str]
    model_sha256: str | None
    reason: str | None


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _paths() -> tuple[Path, Path]:
    model = Path(os.environ.get("ESHB_VISION_MODEL_PATH", DEFAULT_MODEL))
    classes = Path(os.environ.get("ESHB_VISION_CLASSES_PATH", DEFAULT_CLASSES))
    return model, classes


def local_vision_status() -> dict[str, Any]:
    model, classes = _paths()
    dependencies = {
        "numpy": importlib.util.find_spec("numpy") is not None,
        "opencv": importlib.util.find_spec("cv2") is not None,
        "onnxruntime": importlib.util.find_spec("onnxruntime") is not None,
    }
    enabled = os.environ.get("ESHB_VISION_BACKEND", "auto").strip().lower() in {"auto", "local", "hybrid"}
    model_exists = model.exists()
    classes_exists = classes.exists()
    available = enabled and model_exists and classes_exists and all(dependencies.values())
    reason = None
    if not enabled:
        reason = "Local vision backend is disabled by ESHB_VISION_BACKEND."
    elif not model_exists:
        reason = f"No local ONNX model at {model}."
    elif not classes_exists:
        reason = f"No class map at {classes}."
    elif not all(dependencies.values()):
        missing = ", ".join(name for name, ok in dependencies.items() if not ok)
        reason = f"Optional local-vision dependencies are missing: {missing}."
    return asdict(
        LocalVisionConfig(
            enabled=enabled,
            available=available,
            model_path=str(model),
            classes_path=str(classes),
            model_exists=model_exists,
            classes_exists=classes_exists,
            dependencies=dependencies,
            providers=[],
            model_sha256=_sha256(model) if model_exists else None,
            reason=reason,
        )
    )


def _load_classes(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    if isinstance(data, list):
        for index, item in enumerate(data):
            if isinstance(item, str):
                rows.append({"id": index, "gardiner": item})
            elif isinstance(item, dict):
                rows.append({"id": int(item.get("id", index)), **item})
    elif isinstance(data, dict):
        for raw_id, item in data.items():
            if isinstance(item, str):
                rows.append({"id": int(raw_id), "gardiner": item})
            elif isinstance(item, dict):
                rows.append({"id": int(raw_id), **item})
    return sorted(rows, key=lambda row: row["id"])


def _class_metadata(class_id: int, classes: list[dict[str, Any]]) -> dict[str, Any]:
    row = next((item for item in classes if int(item.get("id", -1)) == class_id), {"id": class_id})
    gardiner = row.get("gardiner")
    core = None
    if gardiner:
        for info in CORE_SIGNS.values():
            if (info.gardiner or "").upper() == str(gardiner).upper():
                core = asdict(info)
                break
    return {
        "class_id": class_id,
        "gardiner": gardiner,
        "unicode": row.get("unicode") or (core or {}).get("glyph"),
        "values": row.get("values") or (core or {}).get("values") or [],
        "label": row.get("label") or gardiner or f"class-{class_id}",
        "catalog": row,
        "core_sign": core,
    }


def _iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _nms(rows: list[dict[str, Any]], threshold: float = 0.45) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: row["confidence"], reverse=True)
    kept: list[dict[str, Any]] = []
    while ordered:
        best = ordered.pop(0)
        kept.append(best)
        ordered = [
            row for row in ordered
            if row["class_id"] != best["class_id"] or _iou(row["bbox"], best["bbox"]) < threshold
        ]
    return kept


def _reading_hypotheses(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not detections:
        return []
    # Coordinate ordering is only a hypothesis. Egyptian orientation must normally
    # be resolved from sign facing, layout and artifact context.
    def line_key(row: dict[str, Any]) -> tuple[float, float]:
        x1, y1, x2, y2 = row["bbox"]
        return ((y1 + y2) / 2.0, (x1 + x2) / 2.0)

    ltr = sorted(detections, key=line_key)
    rtl = sorted(detections, key=lambda row: (line_key(row)[0], -line_key(row)[1]))
    return [
        {
            "direction": "left_to_right_candidate",
            "signs": [row["metadata"] for row in ltr],
            "confidence": 0.35,
            "warning": "Pure geometry cannot determine authentic Egyptian reading direction; inspect sign orientation/facing.",
        },
        {
            "direction": "right_to_left_candidate",
            "signs": [row["metadata"] for row in rtl],
            "confidence": 0.35,
            "warning": "Pure geometry cannot determine authentic Egyptian reading direction; inspect sign orientation/facing.",
        },
    ]


@lru_cache(maxsize=1)
def _runtime() -> tuple[Any, str, list[dict[str, Any]], tuple[int, int], list[str]]:
    status = local_vision_status()
    if not status["available"]:
        raise RuntimeError(status["reason"] or "Local vision backend is unavailable.")
    import onnxruntime as ort  # type: ignore

    model = Path(status["model_path"])
    classes = _load_classes(Path(status["classes_path"]))
    requested = [p.strip() for p in os.environ.get("ESHB_VISION_ORT_PROVIDERS", "CUDAExecutionProvider,CPUExecutionProvider").split(",") if p.strip()]
    installed = set(ort.get_available_providers())
    providers = [provider for provider in requested if provider in installed] or ["CPUExecutionProvider"]
    session = ort.InferenceSession(str(model), providers=providers)
    input_meta = session.get_inputs()[0]
    shape = list(input_meta.shape)
    height = int(shape[-2]) if isinstance(shape[-2], int) else 640
    width = int(shape[-1]) if isinstance(shape[-1], int) else 640
    return session, input_meta.name, classes, (height, width), providers


def _letterbox(image: Any, width: int, height: int, cv2: Any, np: Any) -> tuple[Any, float, float, float]:
    source_h, source_w = image.shape[:2]
    scale = min(width / source_w, height / source_h)
    resized_w = max(1, round(source_w * scale))
    resized_h = max(1, round(source_h * scale))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((height, width, 3), 114, dtype=np.uint8)
    pad_x = (width - resized_w) / 2.0
    pad_y = (height - resized_h) / 2.0
    x0, y0 = int(round(pad_x - 0.1)), int(round(pad_y - 0.1))
    canvas[y0:y0 + resized_h, x0:x0 + resized_w] = resized
    return canvas, scale, pad_x, pad_y


def _parse_output(output: Any, conf_threshold: float, input_w: int, input_h: int, np: Any) -> list[dict[str, Any]]:
    arr = np.asarray(output)
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim != 2:
        raise RuntimeError(f"Unsupported detector output shape: {tuple(arr.shape)}")

    # YOLOv8 commonly emits [C,N]; generic exported detectors often emit [N,6]
    # or [N,5+C]. Transpose only when the feature dimension is clearly first.
    if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 512:
        arr = arr.T

    detections: list[dict[str, Any]] = []
    for row in arr:
        values = row.astype(float).tolist()
        if len(values) < 6:
            continue
        if len(values) == 6:
            x1, y1, x2, y2, confidence, class_id = values
            confidence = float(confidence)
            class_id = int(class_id)
        else:
            cx, cy, w, h = values[:4]
            class_scores = values[4:]
            class_id = int(max(range(len(class_scores)), key=lambda i: class_scores[i]))
            confidence = float(class_scores[class_id])
            x1, y1, x2, y2 = cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0
        if confidence < conf_threshold:
            continue
        detections.append({"class_id": class_id, "confidence": confidence, "bbox_model": [x1, y1, x2, y2]})
    return detections


def run_local_detection(raw_image: bytes, mime: str) -> dict[str, Any]:
    status = local_vision_status()
    if not status["available"]:
        raise RuntimeError(status["reason"] or "Local vision backend is unavailable.")
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    session, input_name, classes, (input_h, input_w), providers = _runtime()
    array = np.frombuffer(raw_image, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("OpenCV could not decode the image.")
    source_h, source_w = image.shape[:2]
    boxed, scale, pad_x, pad_y = _letterbox(image, input_w, input_h, cv2, np)
    rgb = cv2.cvtColor(boxed, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))[None, ...]
    output = session.run(None, {input_name: tensor})[0]
    threshold = float(os.environ.get("ESHB_VISION_CONFIDENCE", "0.45"))
    parsed = _parse_output(output, threshold, input_w, input_h, np)

    normalized: list[dict[str, Any]] = []
    for row in parsed:
        x1, y1, x2, y2 = row.pop("bbox_model")
        bbox = [
            max(0.0, min(float(source_w), (x1 - pad_x) / scale)),
            max(0.0, min(float(source_h), (y1 - pad_y) / scale)),
            max(0.0, min(float(source_w), (x2 - pad_x) / scale)),
            max(0.0, min(float(source_h), (y2 - pad_y) / scale)),
        ]
        metadata = _class_metadata(int(row["class_id"]), classes)
        normalized.append({**row, "bbox": bbox, "metadata": metadata})
    normalized = _nms(normalized, float(os.environ.get("ESHB_VISION_NMS_IOU", "0.45")))

    return {
        "backend": "local_onnx",
        "mime": mime,
        "model": {
            "sha256": status["model_sha256"],
            "providers": providers,
            "input_size": [input_w, input_h],
            "class_count": len(classes),
        },
        "image_size": [source_w, source_h],
        "detections": normalized,
        "reading_hypotheses": _reading_hypotheses(normalized),
        "overall_confidence": (sum(row["confidence"] for row in normalized) / len(normalized)) if normalized else 0.0,
        "warning": "Object detection identifies sign candidates, not a complete reading. Direction, grouping, damage, logographic use, determinatives and phonetic complements require epigraphic analysis.",
    }
