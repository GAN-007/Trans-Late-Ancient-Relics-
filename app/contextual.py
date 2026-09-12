from __future__ import annotations

from typing import Any

from .ai import ai_status, contextual_translation_review
from .knowledge import record_unresolved
from .morphology import analyze_transliteration
from .speech import pronunciation_analysis
from .translator import egyptian_to_modern, lexical_candidates, translate_phrase, translate_word


def _deterministic(text: str, source: str, target: str) -> dict[str, Any]:
    if source == "egyptian":
        morphology = analyze_transliteration(text)
        if target == "egyptian":
            from .egyptian import hieroglyphize_phrase
            return {"ok": True, "mode": "render", "morphology": morphology, **hieroglyphize_phrase(text)}
        gloss = egyptian_to_modern(text, target)
        return {"ok": True, "mode": "lexical_gloss", "morphology": morphology, **gloss}

    exact = translate_word(text, source, target="egyptian" if target == "egyptian" else target)
    if exact.get("ok"):
        return exact
    phrase = translate_phrase(text, source)
    for term in phrase.get("unresolved", []):
        record_unresolved(term, source, example_context=text)
    return phrase


def _clarification_questions(deterministic: dict[str, Any], source: str, target: str, context: str) -> list[str]:
    questions: list[str] = []
    ambiguities = deterministic.get("ambiguity") or deterministic.get("alternatives") or []
    unresolved = deterministic.get("unresolved") or []
    morphology = deterministic.get("morphology") or {}
    if ambiguities:
        questions.append("Which sense fits the artifact or conversation context? The current form has more than one plausible lexical meaning.")
    if unresolved:
        questions.append(f"Can you provide more context or a verified spelling for: {', '.join(str(x) for x in unresolved[:6])}?")
    if source == "egyptian" and morphology.get("clause_hints") and not context.strip():
        questions.append("What is the text type and surrounding clause (for example stela, offering formula, title, narrative or letter)? That context can change the grammatical reading.")
    if source == "egyptian" and target in {"english", "swahili"} and not context.strip():
        questions.append("Do you know the period/provenance of the inscription? Diachronic spelling and grammar can affect interpretation.")
    return questions[:4]


def _evidence_tier(deterministic: dict[str, Any]) -> dict[str, Any]:
    mode = deterministic.get("mode")
    if mode == "dictionary":
        return {"tier": "reviewed_lexicon", "confidence_ceiling": 0.95}
    if mode == "grammar_template":
        return {"tier": "pedagogical_grammar_template", "confidence_ceiling": 0.8}
    if mode in {"lexical_gloss", "render"}:
        return {"tier": "lexical_morphological_analysis", "confidence_ceiling": 0.75}
    return {"tier": "analysis_only", "confidence_ceiling": 0.55}


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
    evidence = _evidence_tier(deterministic)
    result: dict[str, Any] = {
        "ok": deterministic.get("ok", False),
        "source": text,
        "source_language": source,
        "target_language": target,
        "register": register,
        "context": context,
        "deterministic": deterministic,
        "evidence": evidence,
        "clarification_questions": _clarification_questions(deterministic, source, target, context),
        "ai": {"used": False, **ai_status()},
    }

    translit = deterministic.get("transliteration")
    if translit:
        result["pronunciation"] = pronunciation_analysis(translit, profile="classroom")["classroom"]
        result["pronunciation_research"] = pronunciation_analysis(translit, profile="consonantal")

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
            # AI is interpretation/ranking evidence, not an attestation source.
            if isinstance(review, dict):
                review["evidence_policy"] = (
                    "AI may rank or explain candidates. Forms outside the deterministic/reviewed evidence layer remain proposed_unverified and cannot raise the historical confidence tier."
                )
                preferred = review.get("preferred_interpretation") or {}
                if isinstance(preferred, dict) and isinstance(preferred.get("confidence"), (int, float)):
                    preferred["confidence"] = min(float(preferred["confidence"]), float(evidence["confidence_ceiling"]))
            result["ai"] = {"used": True, **ai_status(), "review": review}
        except Exception as exc:
            result["ai"] = {"used": False, **ai_status(), "error": str(exc)}
    return result
