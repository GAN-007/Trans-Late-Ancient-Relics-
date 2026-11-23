"""Bridge between the Ancient Language Ladder and modern languages.

The ladder's grammar covers English, Swahili and the ancient stages. Any other modern
language (French, German, Russian, Chinese, Hebrew, …) is connected through English with
the universal machine translator, so a sentence can go from Chinese to Sumerian or from
Old Latin to Russian. Every machine-translated step is labelled as such; the ancient
forms themselves always come from the ladder's grammar, never from the machine translator.
"""
from __future__ import annotations

from typing import Any

from .engine import LADDER_ORDER, LadderError, language_id, translate as ladder_translate
from .grammar import REALIZERS

MODERN_LANGUAGES: dict[str, tuple[str, str]] = {
    "french": ("fr", "French"), "german": ("de", "German"), "russian": ("ru", "Russian"),
    "chinese": ("zh", "Chinese"), "hebrew": ("he", "Hebrew"), "spanish": ("es", "Spanish"),
    "portuguese": ("pt", "Portuguese"), "italian": ("it", "Italian"), "japanese": ("ja", "Japanese"),
    "hindi": ("hi", "Hindi"), "modern_arabic": ("ar", "Arabic (modern)"), "korean": ("ko", "Korean"),
    "turkish": ("tr", "Turkish"), "persian": ("fa", "Persian"), "dutch": ("nl", "Dutch"),
    "ukrainian": ("uk", "Ukrainian"), "polish": ("pl", "Polish"), "urdu": ("ur", "Urdu"),
    "classical_latin": ("la", "Latin (classical)"), "modern_amharic": ("am", "Amharic (modern)"),
}
_CODES = {code: key for key, (code, _name) in MODERN_LANGUAGES.items()}
_NAMES = {name.split(" (")[0].lower(): key for key, (_code, name) in MODERN_LANGUAGES.items()}
_EXTRA = {"mandarin": "chinese", "farsi": "persian", "latin (classical)": "classical_latin", "zh-cn": "chinese"}


def resolve(value: str) -> tuple[str, str]:
    """('ladder', id) for grammar languages, ('modern', key) for machine-translated ones."""
    try:
        return "ladder", language_id(value)
    except LadderError:
        pass
    key = value.strip().lower().replace("-", "_").replace(" ", "_")
    plain = value.strip().lower()
    for candidate in (key, _CODES.get(plain), _NAMES.get(plain), _EXTRA.get(plain)):
        if candidate in MODERN_LANGUAGES:
            return "modern", candidate
    raise LadderError(f"Unknown language '{value}'. Use a ladder language ({', '.join(LADDER_ORDER)}) "
                      f"or a modern one ({', '.join(MODERN_LANGUAGES)}).")


def modern_languages() -> list[dict[str, Any]]:
    return [{"id": key, "code": code, "name": name, "via": "english", "status": "machine_translation"}
            for key, (code, name) in MODERN_LANGUAGES.items()]


def _mt_available() -> bool:
    from ..universal_translation import _provider_status
    return any(p["configured"] for p in _provider_status().values())


async def _mt(text: str, source: str, target: str) -> dict[str, Any]:
    from ..universal_translation import UniversalTranslationRequest, universal_translate
    return await universal_translate(UniversalTranslationRequest(text=text, source_language=source, target_language=target, style="literal"))


NO_MT = ("{name} goes through the universal machine translator, which is not configured "
         "(set UNIVERSAL_MT_BASE_URL or GOOGLE_CLOUD_TRANSLATE_API_KEY).")


async def translate_any(text: str, source: str, targets: str | list[str] = "all") -> dict[str, Any]:
    from ..universal_translation import TranslationError

    src_kind, src = resolve(source)
    target_list = ["all"] if targets in ("all", ["all"], [], None) else ([targets] if isinstance(targets, str) else list(targets))
    resolved = [("ladder", "all")] if target_list == ["all"] else [resolve(t) for t in target_list]
    ladder_targets = [t for kind, t in resolved if kind == "ladder"]
    modern_targets = [t for kind, t in resolved if kind == "modern"]

    if src_kind == "modern" and not ladder_targets:
        return await _modern_only(text, src, modern_targets)

    bridge: dict[str, Any] | None = None
    if src_kind == "modern":
        code, name = MODERN_LANGUAGES[src]
        if not _mt_available():
            raise LadderError(NO_MT.format(name=name))
        try:
            step = await _mt(text, code, "en")
        except TranslationError as exc:
            raise LadderError(f"Machine translation from {name} failed: {exc}") from exc
        bridge = {"from": src, "from_name": name, "english": step["translation"], "provider": step["provider"],
                  "note": f"{name} was machine-translated into English first; the ancient forms come from the ladder's grammar."}
        ladder_source, ladder_text = "english", step["translation"]
    else:
        ladder_source, ladder_text = src, text

    wanted = "all" if ladder_targets == ["all"] else [t for t in ladder_targets if t != ladder_source or src_kind == "modern"]
    need_english = bool(modern_targets)
    if wanted != "all" and need_english and "english" not in wanted and ladder_source != "english":
        wanted = wanted + ["english"]
    result = ladder_translate(ladder_text, ladder_source, wanted)
    result["source"], result["source_language"] = text, src
    if bridge:
        result["bridge"] = bridge
    if not result["ok"]:
        return result

    english = text if ladder_source == "english" and src_kind != "modern" else (
        result["results"].get("english", {}).get("text") or REALIZERS["english"].realize(result["meaning"])["text"])
    for key in modern_targets:
        code, name = MODERN_LANGUAGES[key]
        row: dict[str, Any] = {"language": key, "language_name": name, "status": "machine_translation", "via": "english",
                               "scripts": {}, "gaps": [], "tokens": [], "confidence": 0.0}
        if src_kind == "modern" and key == src:
            row.update(ok=True, text=text, notes=["Your original text."])
        elif not _mt_available():
            row.update(ok=False, text="", status="unavailable", refusal=NO_MT.format(name=name))
        else:
            try:
                step = await _mt(english, "en", code)
                row.update(ok=True, text=step["translation"], provider=step["provider"], confidence=0.6,
                           notes=[f"Machine-translated from the ladder's English ('{english}'); not checked by a person."])
            except TranslationError as exc:
                row.update(ok=False, text="", status="unavailable", refusal=str(exc))
        result["results"][key] = row
    result["targets"] = list(result["results"])
    return result


async def _modern_only(text: str, src: str, targets: list[str]) -> dict[str, Any]:
    """Modern to modern needs no ancient grammar: translate directly."""
    from ..universal_translation import TranslationError

    code, name = MODERN_LANGUAGES[src]
    if not _mt_available():
        raise LadderError(NO_MT.format(name=name))
    results: dict[str, Any] = {}
    for key in targets:
        target_code, target_name = MODERN_LANGUAGES[key]
        try:
            step = await _mt(text, code, target_code)
            results[key] = {"language": key, "language_name": target_name, "ok": True, "text": step["translation"],
                            "status": "machine_translation", "provider": step["provider"], "scripts": {}, "gaps": [],
                            "tokens": [], "confidence": 0.6, "notes": ["Machine translation; not checked by a person."]}
        except TranslationError as exc:
            results[key] = {"language": key, "language_name": target_name, "ok": False, "text": "", "status": "unavailable",
                            "refusal": str(exc), "scripts": {}, "gaps": [], "tokens": [], "confidence": 0.0}
    return {"ok": True, "source": text, "source_language": src, "targets": targets, "meaning": None, "complete": True,
            "parse": {"unknown_words": [], "notes": [], "ambiguities": [], "not_translated": []},
            "accuracy_policy": "Modern-to-modern translation is done directly by the machine translator.", "results": results}
