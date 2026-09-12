from __future__ import annotations

from typing import Any

from .ai import ai_status, contextual_translation_review
from .knowledge import record_unresolved
from .speech import classroom_reading
from .translator import egyptian_to_modern, lexical_candidates, translate_phrase, translate_word


def _deterministic(text: str, source: str, target: str) -> dict[str, Any]:
    if source == "egyptian":
        if target == "egyptian":
            from .egyptian import hieroglyphize_phrase
            return {"ok": True, "mode": "render", **hieroglyphize_phrase(text)}
        return {"ok": True, "mode": "lexical_gloss", **egyptian_to_modern(text, target)}

    exact = translate_word(text, source, target="egyptian" if target == "egyptian" else target)
    if exact.get("ok"):
        return exact
    phrase = translate_phrase(text, source)
    for term in phrase.get("unresolved", []):
        record_unresolved(term, source, example_context=text)
    return phrase


async def contextual_translate(
    text: str,
    source: str,
    target: str,
    context: str = "",
    register: str = "natural",
    use_ai: bool = True,
    max_alternatives: int = 4,
) -> dict[str, Any]:
    deterministic = _deterministic(text, source, target)
    result: dict[str, Any] = {
        "ok": deterministic.get("ok", False),
        "source": text,
        "source_language": source,
        "target_language": target,
        "register": register,
        "context": context,
        "deterministic": deterministic,
        "ai": {"used": False, **ai_status()},
    }

    # Surface pronunciation for Egyptian output without pretending it is exact historical speech.
    translit = deterministic.get("transliteration")
    if translit:
        result["pronunciation"] = classroom_reading(translit)

    # Preserve ambiguity explicitly even without AI.
    alternatives: list[dict[str, Any]] = []
    if source in {"english", "swahili"}:
        for candidate in lexical_candidates(text, source, limit=max_alternatives + 1):
            alternatives.append(
                {
                    "transliteration": candidate["transliteration"],
                    "english": candidate.get("english", []),
                    "swahili": candidate.get("swahili", []),
                    "pos": candidate.get("pos"),
                    "confidence": candidate.get("confidence"),
                }
            )
    result["lexical_alternatives"] = alternatives[:max_alternatives]

    if use_ai and ai_status()["configured"]:
        try:
            review = await contextual_translation_review(
                source_text=text,
                source_language=source,
                target_language=target,
                deterministic_analysis=deterministic,
                context=context,
                register=register,
            )
            result["ai"] = {"used": True, **ai_status(), "review": review}
        except Exception as exc:
            result["ai"] = {"used": False, **ai_status(), "error": str(exc)}
    return result
