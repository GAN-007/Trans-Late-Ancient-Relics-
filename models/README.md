# Local epigraphic vision models

The v3 application contains a production-shaped **adapter** for a local ONNX hieroglyph detector. It intentionally does **not** ship invented or unverified model weights.

## Expected files

By default the server looks for:

```text
models/relic_detector.onnx
models/classes.json
```

Override them with:

```bash
export ESHB_VISION_MODEL_PATH=/models/relic_detector.onnx
export ESHB_VISION_CLASSES_PATH=/models/classes.json
```

Install the optional runtime:

```bash
pip install -r requirements-vision.txt
```

Choose the backend:

```bash
export ESHB_VISION_BACKEND=local   # local ONNX only
export ESHB_VISION_BACKEND=ai      # multimodal provider only
export ESHB_VISION_BACKEND=hybrid  # compare both evidence streams
export ESHB_VISION_BACKEND=auto    # local when available, otherwise AI
```

## Class-map contract

`classes.json` may be a list or object. Each class should identify the training class ID and, when known, Gardiner/Unicode metadata:

```json
[
  {"id": 0, "gardiner": "A1", "unicode": "𓀀", "values": [], "label": "seated man/person"},
  {"id": 1, "gardiner": "F35", "unicode": "𓄤", "values": ["nfr"], "label": "nfr sign"}
]
```

`classes.example.json` is an illustrative schema only. It is **not** a complete Gardiner or Unikemet catalog.

## Model-output contract

The adapter accepts common exported detector tensors:

- `[1, C, N]` or `[1, N, C]` where rows contain `cx, cy, width, height, class_scores...`;
- `[1, N, 6]` / `[N, 6]` where rows contain `x1, y1, x2, y2, confidence, class_id`.

Images are letterboxed rather than stretched, then detections are transformed back to original image coordinates and class-aware NMS is applied.

## Quantization

INT8 may materially improve CPU latency, but **quantization is not automatically safe or accurate**. Calibrate on representative inscription imagery and benchmark the quantized model against a frozen test set before promotion. Do not assume an INT8 export is better merely because it is faster.

## Reading direction

Bounding-box position is never treated as proof of reading direction. Egyptian can be written right-to-left or left-to-right and may use complex group layouts. The adapter emits geometric LTR/RTL hypotheses with deliberately low confidence; orientation/facing and epigraphic context must resolve the reading.

## Training and promotion

Do not replace `relic_detector.onnx` automatically when a correction count threshold is reached. A candidate model must pass:

1. source/license and annotation review;
2. artifact-level train/validation/test separation to prevent frame leakage;
3. per-sign precision/recall and calibration checks;
4. sequence/reading evaluation;
5. damaged-text and unseen-object benchmarks;
6. human epigraphic review;
7. staged rollout with rollback.

The active-learning APIs export reviewed correction metadata for a future training pipeline, but model training/promotion is intentionally external and governed.
