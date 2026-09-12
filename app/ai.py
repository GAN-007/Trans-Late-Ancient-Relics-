from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from .config import settings
from . import storage


class AIUnavailable(RuntimeError):
    pass


async def _post_json(url: str, api_key: str, payload: dict) -> dict:
    if not url:
        raise AIUnavailable("AI endpoint is not configured")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=settings.ai_timeout_seconds) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise ValueError("AI endpoint must return a JSON object")
    return data


def ai_status() -> dict:
    return {
        "text_ai_configured": bool(settings.ai_endpoint),
        "vision_ai_configured": bool(settings.vision_endpoint),
        "mode": "review-gated",
        "policy": "AI may propose alternatives and vocabulary, but only reviewer-approved entries enter the community lexicon.",
    }


async def augment_translation(payload: dict, deterministic_result: dict) -> dict:
    """Optionally ask an external AI reasoner for context-aware alternatives.

    The provider is intentionally vendor-neutral. ESHB_AI_ENDPOINT receives JSON and
    must return a JSON object. No AI output is silently promoted to historical fact.
    """
    if not settings.ai_endpoint:
        return {
            "used": False,
            "provider": "none",
            "message": "No external AI endpoint configured; deterministic linguistic engine used.",
            "alternatives": [],
        }
    request_payload = {
        "task": "ancient_egyptian_contextual_translation_review",
        "source_text": payload.get("text"),
        "source_language": payload.get("source"),
        "target_language": payload.get("target"),
        "context": payload.get("context", ""),
        "intent": payload.get("intent", ""),
        "translation_mode": payload.get("mode", "careful"),
        "deterministic_analysis": deterministic_result,
        "requirements": {
            "preserve_ambiguity": True,
            "separate_literal_and_natural": True,
            "never_claim_unattested_spelling_as_attested": True,
            "return_alternatives": True,
            "return_rationale": True,
            "return_confidence": True,
        },
    }
    try:
        response = await _post_json(settings.ai_endpoint, settings.ai_api_key, request_payload)
        return {"used": True, "provider": "external", "response": response}
    except Exception as exc:
        return {"used": False, "provider": "external_error", "message": str(exc), "alternatives": []}


def validate_image_data_url(data_url: str) -> tuple[str, bytes]:
    if not data_url.startswith("data:image/") or ";base64," not in data_url:
        raise ValueError("Expected a base64 image data URL")
    header, encoded = data_url.split(",", 1)
    mime = header[5:].split(";", 1)[0]
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) > settings.max_image_bytes:
        raise ValueError("Image exceeds configured maximum size")
    return mime, raw


async def analyze_image(image_data_url: str, target_language: str, context: str = "") -> dict:
    mime, raw = validate_image_data_url(image_data_url)
    if not settings.vision_endpoint:
        return {
            "ok": False,
            "status": "vision_provider_not_configured",
            "message": "Camera capture works, but automatic glyph recognition requires ESHB_VISION_ENDPOINT. The app will never pretend it recognized signs when no vision model is configured.",
            "image": {"mime": mime, "bytes": len(raw)},
        }
    payload = {
        "task": "ancient_egyptian_inscription_analysis",
        "image_data_url": image_data_url,
        "target_language": target_language,
        "context": context,
        "output_contract": {
            "reading_direction": "string|null",
            "signs": "array of {glyph?, gardiner?, confidence, bbox?}",
            "transliteration_candidates": "array",
            "translation_candidates": "array",
            "uncertainties": "array",
            "notes": "string",
        },
    }
    try:
        data = await _post_json(settings.vision_endpoint, settings.vision_api_key, payload)
        return {"ok": True, "status": "analyzed", "provider": "external", "analysis": data, "image": {"mime": mime, "bytes": len(raw)}}
    except Exception as exc:
        return {"ok": False, "status": "vision_provider_error", "message": str(exc), "image": {"mime": mime, "bytes": len(raw)}}


async def propose_from_learning_insights(min_frequency: int = 3, limit: int = 20, user_id: int | None = None) -> dict:
    insights = storage.learning_insights(limit=200)
    terms = [x for x in insights["unresolved_terms"] if x["count"] >= min_frequency][:limit]
    if not terms:
        return {"ok": True, "created": [], "message": "No unresolved terms currently meet the frequency threshold."}
    if not settings.ai_endpoint:
        return {
            "ok": False,
            "created": [],
            "research_queue": terms,
            "message": "Repeated unresolved terms were identified. Configure ESHB_AI_ENDPOINT to generate review-only vocabulary proposals, or let a contributor research them manually.",
        }
    request_payload = {
        "task": "propose_ancient_egyptian_lexicon_research_candidates",
        "unresolved_terms": terms,
        "constraints": {
            "do_not_invent": True,
            "require_evidence_notes": True,
            "output": "entries",
            "schema": {
                "transliteration": "string",
                "english": ["string"],
                "swahili": ["string"],
                "pos": "string",
                "hieroglyphs": "string|null",
                "gardiner": ["string"],
                "mdc": "string|null",
                "notes": "string",
                "evidence": "string",
                "confidence": "proposed|medium|high",
            },
        },
    }
    try:
        response = await _post_json(settings.ai_endpoint, settings.ai_api_key, request_payload)
    except Exception as exc:
        return {"ok": False, "created": [], "research_queue": terms, "message": str(exc)}
    entries = response.get("entries", []) if isinstance(response, dict) else []
    created = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict) or not entry.get("transliteration") or not entry.get("english") or not entry.get("swahili"):
            continue
        created.append(storage.create_proposal(user_id, entry, ai_generated=True))
    return {
        "ok": True,
        "created": created,
        "research_queue": terms,
        "message": "AI suggestions are pending human review and are not yet part of the authoritative learner lexicon.",
    }
