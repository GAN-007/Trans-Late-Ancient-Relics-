"""Provider-routed modern-language translation without changing historical Egyptian evidence.

Hy-MT2 runs on a separately deployed OpenAI-compatible chat-completions server.
Google Cloud Translation Basic v2 is an optional broader-language provider.
No downloaded weights, undocumented Google Translate scraping, or guessed
historical/script/sign-language support are bundled with this application.
"""
from __future__ import annotations

import html
import json
import os
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, field_validator

HY_LANGUAGES: dict[str, str] = {
    "zh": "Chinese", "en": "English", "fr": "French", "pt": "Portuguese",
    "es": "Spanish", "ja": "Japanese", "tr": "Turkish", "ru": "Russian",
    "ar": "Arabic", "ko": "Korean", "th": "Thai", "it": "Italian",
    "de": "German", "vi": "Vietnamese", "ms": "Malay", "id": "Indonesian",
    "tl": "Filipino", "hi": "Hindi", "zh-Hant": "Traditional Chinese",
    "pl": "Polish", "cs": "Czech", "nl": "Dutch", "km": "Khmer",
    "my": "Burmese", "fa": "Persian", "gu": "Gujarati", "ur": "Urdu",
    "te": "Telugu", "mr": "Marathi", "he": "Hebrew", "bn": "Bengali",
    "ta": "Tamil", "uk": "Ukrainian", "bo": "Tibetan",
    "kk": "Kazakh", "mn": "Mongolian", "ug": "Uyghur", "yue": "Cantonese",
}
ALIASES = {value.lower(): code for code, value in HY_LANGUAGES.items()}
ALIASES.update({"swahili": "sw", "kiswahili": "sw", "zh-cn": "zh",
                "zh-tw": "zh-Hant", "fil": "tl", "burmese": "my",
                "auto": "auto", "egyptian": "egyptian",
                "middle egyptian": "egyptian"})
SAFE_LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
PROTECTED = re.compile(
    r"\{\{[^{}\n]+\}\}|\$\{[^{}\n]+\}|%(?:\d+\$)?[-+#0 ]?\d*(?:\.\d+)?[sdif]|"
    r"</?[A-Za-z][^>\n]*>|https?://[^\s<>]+"
)
TRANSLATABLE_KEYS = frozenset({
    "title", "text", "label", "message", "description", "summary",
    "content", "body", "caption", "subtitle", "alt", "placeholder",
    "tooltip", "question", "answer", "notice", "instructions",
})
SRT_TIME = re.compile(
    r"^(?:\d{2,3}:)?\d{2}:\d{2}[,.]\d{3}\s+-->\s+"
    r"(?:\d{2,3}:)?\d{2}:\d{2}[,.]\d{3}(?:\s+.*)?$"
)


class TranslationError(Exception):
    """Client-visible, non-secret-bearing translation error."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class UniversalTranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    source_language: str = Field(default="auto", min_length=2, max_length=40)
    target_language: str = Field(min_length=2, max_length=40)
    provider: Literal["auto", "hy-mt2", "google-cloud"] = "auto"
    format: Literal["text", "json", "srt"] = "text"
    style: Literal["natural", "formal", "informal", "literal"] = "natural"
    context: str = Field(default="", max_length=1500)
    glossary: dict[str, str] = Field(default_factory=dict)
    translatable_keys: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("glossary")
    @classmethod
    def validate_glossary(cls, glossary: dict[str, str]) -> dict[str, str]:
        if len(glossary) > 30:
            raise ValueError("A maximum of 30 glossary entries is supported.")
        if any(not 0 < len(k) <= 100 or not 0 < len(v) <= 100 for k, v in glossary.items()):
            raise ValueError("Glossary terms must contain 1 to 100 characters.")
        return glossary

    @field_validator("translatable_keys")
    @classmethod
    def validate_keys(cls, keys: list[str]) -> list[str]:
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key) for key in keys):
            raise ValueError("Invalid translatable JSON key.")
        return keys


def _language_code(language: str) -> str:
    cleaned = language.strip()
    code = ALIASES.get(cleaned.lower(), cleaned)
    if code.lower() == "auto":
        return "auto"
    if code.lower() in {"egyptian", "ancient-egyptian", "und", "unknown"}:
        raise TranslationError(
            "Unverified ancient or unidentified languages must use the specialist evidence-aware pipeline."
        )
    if code.lower() == "zh-hant":
        return "zh-Hant"
    code = code.lower()
    if not SAFE_LANGUAGE.fullmatch(code):
        raise TranslationError("Use a supported language name or a valid BCP-47-style language code.")
    return code


def _provider_status() -> dict[str, Any]:
    hy = bool(os.getenv("UNIVERSAL_MT_BASE_URL", "").strip())
    google = bool(os.getenv("GOOGLE_CLOUD_TRANSLATE_API_KEY", "").strip())
    return {
        "hy-mt2": {
            "configured": hy,
            "model": os.getenv("UNIVERSAL_MT_MODEL", "tencent/Hy-MT2-1.8B") if hy else None,
            "catalogue": sorted(HY_LANGUAGES),
            "language_coverage": "Hy-MT2 documented set; text only",
        },
        "google-cloud": {
            "configured": google,
            "model": "Cloud Translation Basic v2" if google else None,
            "language_coverage": "Query the official Google Cloud API for current coverage",
        },
    }


def universal_capabilities() -> dict[str, Any]:
    return {
        "providers": _provider_status(),
        "format_support": ["text", "json", "srt"],
        "modalities": {
            "typed_text": "implemented_when_provider_configured",
            "structured_json": "implemented_when_provider_configured",
            "srt_subtitles": "implemented_when_provider_configured",
            "egyptian_historical": "existing_specialist_pipeline_only",
            "camera_ocr": "existing_optional_vision_pipeline",
            "audio": "existing_browser_speech_features_only",
            "sign_language_video": "not_implemented_requires_language_specific_dataset_and_model",
            "radio_waves_unknown_signals": "not_implemented_requires_signal_decoding_and_semantic_protocol",
        },
        "historical_evidence_boundary": "Neural translation is not epigraphic attestation.",
        "automatic_model_promotion": False,
    }


def _choose_provider(requested: str, source: str, target: str) -> str:
    statuses = _provider_status()
    if requested != "auto":
        if not statuses[requested]["configured"]:
            raise TranslationError(f"{requested} is not configured on this server.", 503)
        if requested == "hy-mt2" and (
            source == "auto" or source not in HY_LANGUAGES or target not in HY_LANGUAGES
        ):
            raise TranslationError(
                "Hy-MT2 requires explicit source and target languages from its documented language set."
            )
        return requested
    if statuses["hy-mt2"]["configured"] and source in HY_LANGUAGES and target in HY_LANGUAGES:
        return "hy-mt2"
    if statuses["google-cloud"]["configured"]:
        return "google-cloud"
    raise TranslationError(
        "No compatible translation provider configured. Set UNIVERSAL_MT_BASE_URL "
        "for supported Hy-MT2 pairs or GOOGLE_CLOUD_TRANSLATE_API_KEY for Google Cloud.",
        503,
    )


def _mask(text: str) -> tuple[str, dict[str, str]]:
    originals: dict[str, str] = {}
    # Use a marker namespace absent from input and use predictable indices.
    prefix = "GANPRESERVE"
    while prefix in text:
        prefix += "X"

    def replace(match: re.Match[str]) -> str:
        marker = f"__{prefix}_{len(originals):04d}__"
        originals[marker] = match.group(0)
        return marker

    return PROTECTED.sub(replace, text), originals


def _unmask(translated: str, originals: dict[str, str]) -> str:
    for marker, original in originals.items():
        if translated.count(marker) != 1:
            raise TranslationError(
                "Translation failed integrity validation: a code, tag, URL, or placeholder changed.",
                502,
            )
        translated = translated.replace(marker, original, 1)
    return translated


def _prompt(text: str, src: str, tgt: str, req: UniversalTranslationRequest) -> str:
    source_name = HY_LANGUAGES.get(src, src)
    target_name = HY_LANGUAGES.get(tgt, tgt)
    lines = [
        f"Translate the following text from {source_name} to {target_name}.",
        "Return ONLY the translated text without preface, markdown fences or explanation.",
        f"Translation style: {req.style}.",
        "Preserve all __GANPRESERVE...__ tokens byte-for-byte exactly once in their original order.",
    ]
    if req.context:
        lines.append("Context for disambiguation: " + req.context)
    if req.glossary:
        lines.append("Required terminology, preserving exact target spellings:")
        lines.extend(f"{source} translates to {target}" for source, target in req.glossary.items())
    lines.append("Text to translate:\n" + text)
    return "\n".join(lines)


async def _call_hy(text: str, src: str, tgt: str, req: UniversalTranslationRequest) -> str:
    base = os.environ["UNIVERSAL_MT_BASE_URL"].strip().rstrip("/")
    # Never take this endpoint from the HTTP request; only the server operator configures it.
    if not (base.startswith("https://") or base.startswith("http://127.0.0.1")
            or base.startswith("http://localhost") or base.startswith("http://[::1]")):
        raise TranslationError("Hy-MT2 endpoint must use HTTPS or a local loopback URL.", 503)
    if not base.endswith("/v1"):
        base += "/v1"
    model = os.getenv("UNIVERSAL_MT_MODEL", "tencent/Hy-MT2-1.8B")
    large = "30B-A3B" in model
    body = {
        "model": model,
        "messages": [{"role": "user", "content": _prompt(text, src, tgt, req)}],
        "max_tokens": 4096,
        "temperature": 0.7,
        "top_p": 1.0 if large else 0.6,
    }
    headers = {"Content-Type": "application/json"}
    if os.getenv("UNIVERSAL_MT_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["UNIVERSAL_MT_API_KEY"]
    try:
        timeout = min(180.0, max(5.0, float(os.getenv("UNIVERSAL_MT_TIMEOUT", "60"))))
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(base + "/chat/completions", json=body, headers=headers)
            response.raise_for_status()
            result = response.json()
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str) or not content.strip():
            raise TranslationError("Hy-MT2 returned an empty translation.", 502)
        return content.strip()
    except TranslationError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise TranslationError(
            f"Hy-MT2 inference request failed ({type(exc).__name__}); verify the configured server and model.",
            502,
        ) from exc


async def _call_google(text: str, src: str, tgt: str, req: UniversalTranslationRequest) -> str:
    data: dict[str, str] = {"q": text, "target": tgt, "format": "text"}
    if src != "auto":
        data["source"] = src
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=False) as client:
            response = await client.post(
                "https://translation.googleapis.com/language/translate/v2",
                params={"key": os.environ["GOOGLE_CLOUD_TRANSLATE_API_KEY"]},
                json=data,
            )
            response.raise_for_status()
            result = response.json()
        content = result["data"]["translations"][0]["translatedText"]
        if not isinstance(content, str) or not content.strip():
            raise TranslationError("Google Cloud returned an empty translation.", 502)
        return html.unescape(content)
    except TranslationError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise TranslationError(
            f"Google Cloud Translation request failed ({type(exc).__name__}); check API access, billing and language support.",
            502,
        ) from exc


async def _translate_leaf(
    text: str, source: str, target: str, provider: str, req: UniversalTranslationRequest
) -> str:
    if not text.strip():
        return text
    if source == target:
        return text
    masked, protected = _mask(text)
    translated = await (
        _call_hy(masked, source, target, req)
        if provider == "hy-mt2"
        else _call_google(masked, source, target, req)
    )
    translated = _unmask(translated, protected)
    for original, required in req.glossary.items():
        if original.casefold() in text.casefold() and required.casefold() not in translated.casefold():
            raise TranslationError(
                "Translation failed terminology validation for a required glossary entry.",
                502,
            )
    return translated


async def _translate_json(
    text: str, source: str, target: str, provider: str, req: UniversalTranslationRequest
) -> tuple[str, int]:
    try:
        root = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranslationError("Invalid JSON: " + exc.msg) from exc
    permitted = TRANSLATABLE_KEYS | frozenset(req.translatable_keys)
    count = 0

    async def walk(value: Any, translate_strings: bool = False, depth: int = 0) -> Any:
        nonlocal count
        if depth > 30:
            raise TranslationError("JSON nesting exceeds the 30-level safety limit.")
        if isinstance(value, dict):
            return {key: await walk(v, key in permitted, depth + 1) for key, v in value.items()}
        if isinstance(value, list):
            return [await walk(v, translate_strings, depth + 1) for v in value]
        if isinstance(value, str) and translate_strings and value.strip():
            count += 1
            if count > 100:
                raise TranslationError("Structured translation is limited to 100 text fields.")
            return await _translate_leaf(value, source, target, provider, req)
        return value

    converted = await walk(root)
    return json.dumps(converted, ensure_ascii=False, indent=2), count


async def _translate_srt(
    text: str, source: str, target: str, provider: str, req: UniversalTranslationRequest
) -> tuple[str, int]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    cues = re.split(r"\n\s*\n", normalized)
    if len(cues) > 100:
        raise TranslationError("Subtitle requests are limited to 100 cues.")
    output: list[str] = []
    for cue in cues:
        lines = cue.split("\n")
        clock_index = next((i for i, line in enumerate(lines[:2]) if SRT_TIME.fullmatch(line)), -1)
        if clock_index < 0 or not any(line.strip() for line in lines[clock_index + 1:]):
            raise TranslationError("Invalid SRT: each cue requires a time range and subtitle text.")
        header = lines[:clock_index + 1]
        spoken = "\n".join(lines[clock_index + 1:])
        translated = await _translate_leaf(spoken, source, target, provider, req)
        output.append("\n".join(header + [translated]))
    return "\n\n".join(output) + "\n", len(output)


async def universal_translate(req: UniversalTranslationRequest) -> dict[str, Any]:
    source, target = _language_code(req.source_language), _language_code(req.target_language)
    if target == "auto":
        raise TranslationError("Specify a target language.")
    provider = _choose_provider(req.provider, source, target)
    if req.format == "json":
        translation, segments = await _translate_json(req.text, source, target, provider, req)
    elif req.format == "srt":
        translation, segments = await _translate_srt(req.text, source, target, provider, req)
    else:
        translation = await _translate_leaf(req.text, source, target, provider, req)
        segments = 1
    return {
        "ok": True,
        "source_language": source,
        "target_language": target,
        "provider": provider,
        "model": _provider_status()[provider]["model"],
        "format": req.format,
        "segments": segments,
        "translation": translation,
        "verified_historical_translation": False,
        "safety_note": "Neural output is not evidence for ancient-language readings or unknown communication signals.",
    }
