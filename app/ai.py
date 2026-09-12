from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .runtime import env_bool

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.6"


def ai_status() -> dict[str, Any]:
    provider = os.environ.get("ESHB_AI_PROVIDER", "openai" if os.environ.get("OPENAI_API_KEY") else "disabled").strip().lower()
    configured = provider == "openai" and bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "provider": provider,
        "configured": configured,
        "model": os.environ.get("ESHB_AI_MODEL", DEFAULT_MODEL) if configured else None,
        "vision": configured,
        "contextual_translation": configured,
        "knowledge_proposals": configured,
        "stores_images": False,
    }


def _extract_output_text(payload: dict[str, Any]) -> str:
    # The Responses API returns message output items whose content includes output_text blocks.
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    # Some compatible gateways expose a convenience field.
    if not chunks and isinstance(payload.get("output_text"), str):
        chunks.append(payload["output_text"])
    return "\n".join(chunks).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.I)
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
        if not isinstance(data, dict):
            raise ValueError("AI output must be a JSON object.")
        return data
    except json.JSONDecodeError as exc:
        # Last-resort extraction of one JSON object from explanatory text.
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(stripped[start : end + 1])
            if isinstance(data, dict):
                return data
        raise ValueError("AI provider returned non-JSON output.") from exc


async def _responses_request(input_content: list[dict[str, Any]], instructions: str) -> dict[str, Any]:
    status = ai_status()
    if not status["configured"]:
        raise RuntimeError("AI provider is not configured.")
    base_url = os.environ.get("ESHB_AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("ESHB_AI_MODEL", DEFAULT_MODEL)
    api_key = os.environ["OPENAI_API_KEY"]
    body = {
        "model": model,
        "instructions": instructions,
        "input": [{"role": "user", "content": input_content}],
    }
    timeout = float(os.environ.get("ESHB_AI_TIMEOUT_SECONDS", "60"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    return _parse_json_text(_extract_output_text(payload))


async def analyze_relic_image(image_data_url: str, target_language: str, context: str = "", detail: str = "high") -> dict[str, Any]:
    instructions = """
You are an epigraphy assistant for an Ancient Egyptian learning application. Analyze only what the image supports.
Do not pretend that every mark is readable. Distinguish Egyptian hieroglyphs from decorative pseudo-hieroglyphs and from other scripts.
Return ONLY a JSON object with these keys:
script_detected (string), reading_direction (string or null), sign_candidates (array of objects with unicode, gardiner, value, confidence),
transliteration_candidates (array of objects with text, confidence, rationale),
translation_candidates (array of objects with language, text, confidence, rationale),
determinatives (array), phonetic_complements (array), uncertainties (array of strings),
recommended_next_step (string), overall_confidence (number 0..1).
For translation, preserve ambiguity and provide multiple candidates when warranted. Never invent a Gardiner code if unsure; use null.
Treat exact historical pronunciation as uncertain. If the image is not readable Ancient Egyptian, say so clearly.
""".strip()
    prompt = (
        f"Target explanatory language: {target_language}. "
        f"User context: {context or 'none supplied'}. "
        "Inspect this frame from a live camera or uploaded image and produce the structured epigraphic analysis."
    )
    return await _responses_request(
        [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": image_data_url, "detail": detail},
        ],
        instructions,
    )


async def contextual_translation_review(
    source_text: str,
    source_language: str,
    target_language: str,
    deterministic_analysis: dict[str, Any],
    context: str = "",
    register: str = "natural",
) -> dict[str, Any]:
    instructions = """
You are a cautious Middle Egyptian linguistic reviewer. Your job is to rank meanings and explain ambiguity, not to fabricate certainty.
The application provides a deterministic dictionary/grammar analysis. Use it as the authoritative candidate pool.
If you suggest an Egyptian form not present in that analysis, mark it proposed_unverified=true and explain that it requires Egyptological review.
Return ONLY JSON with keys: preferred_interpretation, alternatives, ambiguity_notes, intent_notes, confidence, proposed_unverified_forms.
preferred_interpretation must contain text, rationale and confidence. alternatives is an array of the same shape.
Do not claim reconstructed vowels are certain. Prefer meaning and syntax over decorative letter substitution.
""".strip()
    payload = {
        "source_text": source_text,
        "source_language": source_language,
        "target_language": target_language,
        "context": context,
        "register": register,
        "deterministic_analysis": deterministic_analysis,
    }
    return await _responses_request(
        [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
        instructions,
    )


async def propose_lexicon_entry(term: str, source_language: str, context: str = "") -> dict[str, Any]:
    instructions = """
You draft candidate entries for a human-reviewed Middle Egyptian learner dictionary. Never mark a draft as verified.
Return ONLY JSON with keys: transliteration, english, swahili, pos, notes, confidence, evidence_needed, rationale.
english and swahili must be arrays. confidence must be low, medium or high.
If you cannot responsibly suggest a Middle Egyptian lemma, return transliteration as an empty string and explain why in rationale.
Do not invent citations or claim attestation. The reviewer must later add a real source before approval.
""".strip()
    payload = {"term": term, "source_language": source_language, "context": context}
    return await _responses_request(
        [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
        instructions,
    )
