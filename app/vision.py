from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from typing import Any

from .ai import ai_status, analyze_relic_image
from .epigraphy import analyze_hieroglyphic_text
from .vision_local import local_vision_status, run_local_detection

DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\r\n]+)$", re.I)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
VALID_BACKENDS = {"auto", "local", "ai", "hybrid"}


def decode_image_data_url(data_url: str) -> tuple[dict[str, Any], bytes]:
    match = DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValueError("Image must be a PNG, JPEG or WebP data URL.")
    mime = match.group(1).lower()
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 image data.") from exc
    if not raw:
        raise ValueError("Image is empty.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds the {MAX_IMAGE_BYTES // (1024*1024)} MB limit.")
    valid = False
    if mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        valid = True
    elif mime == "image/jpeg" and raw.startswith(b"\xff\xd8"):
        valid = True
    elif mime == "image/webp" and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        valid = True
    if not valid:
        raise ValueError("Image bytes do not match the declared image type.")
    metadata = {"mime": mime, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return metadata, raw


def validate_image_data_url(data_url: str) -> dict[str, Any]:
    metadata, _raw = decode_image_data_url(data_url)
    return metadata


def vision_status() -> dict[str, Any]:
    requested = os.environ.get("ESHB_VISION_BACKEND", "auto").strip().lower()
    if requested not in VALID_BACKENDS:
        requested = "auto"
    local = local_vision_status()
    ai = ai_status()
    if requested == "local":
        usable = bool(local["available"])
        resolved = "local" if usable else "unavailable"
    elif requested == "ai":
        usable = bool(ai["configured"])
        resolved = "ai" if usable else "unavailable"
    elif requested == "hybrid":
        usable = bool(local["available"] or ai["configured"])
        resolved = "hybrid" if local["available"] and ai["configured"] else "local" if local["available"] else "ai" if ai["configured"] else "unavailable"
    else:
        usable = bool(local["available"] or ai["configured"])
        resolved = "local" if local["available"] else "ai" if ai["configured"] else "unavailable"
    return {
        "requested_backend": requested,
        "resolved_backend": resolved,
        "available": usable,
        "local": local,
        "ai": ai,
        "privacy_default": "Frames are analyzed transiently. Active-learning image retention is a separate explicit-consent workflow.",
    }


def _local_to_analysis(local: dict[str, Any]) -> dict[str, Any]:
    detections = local.get("detections", [])
    sign_candidates: list[dict[str, Any]] = []
    glyphs: list[str] = []
    for detection in detections:
        metadata = detection.get("metadata", {})
        glyph = metadata.get("unicode")
        if glyph:
            glyphs.append(str(glyph))
        values = metadata.get("values") or []
        sign_candidates.append(
            {
                "unicode": glyph,
                "gardiner": metadata.get("gardiner"),
                "value": values[0] if values else None,
                "values": values,
                "confidence": float(detection.get("confidence", 0.0)),
                "bbox": detection.get("bbox"),
                "source": "local_onnx",
            }
        )

    transliterations: list[dict[str, Any]] = []
    for hypothesis in local.get("reading_hypotheses", []):
        values = []
        for sign in hypothesis.get("signs", []):
            sign_values = sign.get("values") or []
            values.append(sign_values[0] if sign_values else "?")
        if values:
            transliterations.append(
                {
                    "text": "".join(values),
                    "confidence": float(hypothesis.get("confidence", 0.0)),
                    "rationale": f"{hypothesis.get('direction')}: geometry-only ordering. Sign orientation and grouping must confirm the direction.",
                }
            )

    epigraphy = analyze_hieroglyphic_text("".join(glyphs)) if glyphs else None
    uncertainties = [
        "Detector confidence is not linguistic confidence.",
        "Reading direction is unresolved unless sign orientation or artifact context establishes it.",
        "Detected signs may function as phonograms, logograms, determinatives or phonetic complements depending on context.",
    ]
    return {
        "script_detected": "Ancient Egyptian hieroglyphic sign candidates" if detections else "no confident local sign detections",
        "reading_direction": "undetermined",
        "sign_candidates": sign_candidates,
        "transliteration_candidates": transliterations,
        "translation_candidates": [],
        "determinatives": (epigraphy or {}).get("determinative_candidates", []),
        "phonetic_complements": (epigraphy or {}).get("phonetic_complement_candidates", []),
        "uncertainties": uncertainties,
        "recommended_next_step": "Confirm reading direction and sign groups, then run morphological/syntactic analysis before choosing a translation.",
        "overall_confidence": float(local.get("overall_confidence", 0.0)),
        "epigraphy": epigraphy,
        "local_detector": local,
    }


def _merge_hybrid(local_analysis: dict[str, Any], ai_analysis: dict[str, Any]) -> dict[str, Any]:
    # Keep both evidence streams visible. The AI is not permitted to overwrite a
    # local detector observation invisibly; disagreements are surfaced for review.
    local_signs = local_analysis.get("sign_candidates", [])
    ai_signs = ai_analysis.get("sign_candidates", []) if isinstance(ai_analysis, dict) else []
    local_codes = {str(item.get("gardiner")) for item in local_signs if item.get("gardiner")}
    ai_codes = {str(item.get("gardiner")) for item in ai_signs if item.get("gardiner")}
    disagreements = sorted((local_codes ^ ai_codes))
    merged = dict(ai_analysis) if isinstance(ai_analysis, dict) else {}
    merged["local_detector_analysis"] = local_analysis
    merged["evidence_comparison"] = {
        "local_gardiner_candidates": sorted(local_codes),
        "ai_gardiner_candidates": sorted(ai_codes),
        "disagreements": disagreements,
        "agreement": sorted(local_codes & ai_codes),
        "policy": "Disagreement lowers trust; neither source silently overrides the other.",
    }
    merged_uncertainties = list(merged.get("uncertainties") or [])
    if disagreements:
        merged_uncertainties.append(f"Local detector and multimodal reviewer disagree on sign candidates: {', '.join(disagreements)}")
    merged["uncertainties"] = merged_uncertainties
    ai_conf = float(merged.get("overall_confidence", 0.0) or 0.0)
    local_conf = float(local_analysis.get("overall_confidence", 0.0) or 0.0)
    if local_conf and ai_conf:
        merged["overall_confidence"] = min(ai_conf, local_conf) if disagreements else (ai_conf + local_conf) / 2.0
    return merged


async def analyze_frame(data_url: str, target_language: str = "english", context: str = "", detail: str = "high") -> dict[str, Any]:
    metadata, raw = decode_image_data_url(data_url)
    status = vision_status()
    requested = status["requested_backend"]
    local_result: dict[str, Any] | None = None
    ai_result: dict[str, Any] | None = None

    wants_local = requested in {"auto", "local", "hybrid"} and status["local"]["available"]
    wants_ai = requested in {"ai", "hybrid"} and status["ai"]["configured"]
    if requested == "auto" and not wants_local and status["ai"]["configured"]:
        wants_ai = True

    if wants_local:
        local_result = run_local_detection(raw, metadata["mime"])
    if wants_ai:
        ai_result = await analyze_relic_image(data_url, target_language, context=context, detail=detail)

    if local_result and ai_result:
        analysis = _merge_hybrid(_local_to_analysis(local_result), ai_result)
        backend = "hybrid"
    elif local_result:
        analysis = _local_to_analysis(local_result)
        backend = "local_onnx"
    elif ai_result:
        analysis = ai_result
        backend = "multimodal_ai"
    else:
        return {
            "ok": False,
            "image": metadata,
            "vision": status,
            "message": "Camera capture works, but no vision backend is currently available. Configure a multimodal provider or install a reviewed ONNX detector plus class map.",
            "privacy": "The server validated the frame and did not persist it.",
        }

    return {
        "ok": True,
        "backend": backend,
        "image": metadata,
        "vision": status,
        "analysis": analysis,
        "privacy": "The application analyzed this frame transiently and did not persist it. Research-image retention occurs only through the separate opt-in correction workflow.",
    }
