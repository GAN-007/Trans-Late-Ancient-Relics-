"""Any-to-any translation across the Ancient Language Ladder.

Pipeline: source text -> parser -> language-neutral frame -> target realizer.
Because every language goes through the same frame, English, Swahili and all
ancient stages translate into each other in both directions.
"""
from __future__ import annotations

from typing import Any

from .grammar import REALIZERS
from .lexicon import adjectives, nouns, verbs
from .parsing import parse

ALIASES = {
    "en": "english", "eng": "english",
    "sw": "swahili", "swa": "swahili", "kiswahili": "swahili",
    "sumerian": "archaic_sumerian", "sux": "archaic_sumerian",
    "akkadian": "old_akkadian", "akk": "old_akkadian", "old akkadian": "old_akkadian", "babylonian": "old_akkadian",
    "latin": "old_latin", "la": "old_latin",
    "arabic": "old_arabic", "ar": "old_arabic",
    "ge'ez": "geez", "gez": "geez", "ethiopic": "geez",
    "amharic": "old_amharic", "am": "old_amharic",
    "proto-semitic": "proto_semitic", "sem": "proto_semitic",
    "proto-world": "proto_world", "pw": "proto_world",
    "hieroglyphic": "archaic_hieroglyphic", "proto-hieroglyphic": "archaic_hieroglyphic",
    "egyptian": "old_egyptian", "egy": "old_egyptian",
    "middle egyptian": "middle_egyptian",
}

LADDER_ORDER = [
    "english", "swahili", "old_amharic", "geez", "old_arabic", "old_latin",
    "middle_egyptian", "old_egyptian", "archaic_sumerian", "old_akkadian", "archaic_hieroglyphic",
    "proto_semitic", "proto_world",
]

ACCURACY_POLICY = (
    "Single words carry their attestation status. Sentences are composed by grammar rules from attested "
    "or reconstructed words; they are teaching reconstructions, not quotations from ancient texts. "
    "Akkadian cuneiform is shown in a standard syllabic spelling. Proto-Semitic is reconstructed, Proto-World is a hypothesis most linguists reject, and archaic "
    "hieroglyphic writing did not record full sentences."
)


class LadderError(ValueError):
    pass


def language_id(value: str) -> str:
    key = value.strip().lower().replace("-", "_") if value else ""
    if key in REALIZERS:
        return key
    key2 = value.strip().lower()
    if key2 in ALIASES:
        return ALIASES[key2]
    if key2.replace("_", "-") in ALIASES:
        return ALIASES[key2.replace("_", "-")]
    raise LadderError(f"Unknown language '{value}'. Use one of: {', '.join(LADDER_ORDER)}.")


def languages() -> list[dict[str, Any]]:
    out = []
    for lang in LADDER_ORDER:
        r = REALIZERS[lang]
        out.append({
            "id": r.id, "name": r.name, "status": r.status, "period": r.period, "family": r.family,
            "writing": r.writing, "word_order": r.order, "notes": list(r.notes),
            "can_parse": True, "can_generate_sentences": lang not in {"proto_world", "archaic_hieroglyphic"},
        })
    return out


def coverage() -> dict[str, Any]:
    codes = {"archaic_sumerian": "sux", "old_akkadian": "akk", "old_latin": "la", "old_arabic": "ar", "geez": "gez", "old_amharic": "am",
             "proto_semitic": "sem", "proto_world": "pw", "old_egyptian": "egy"}
    table = {}
    for lang, code in codes.items():
        table[lang] = {
            "nouns": sum(1 for n in nouns().values() if n.get(code)),
            "adjectives": sum(1 for a in adjectives().values() if a.get(code)),
            "verbs": sum(1 for v in verbs().values() if v.get(code)),
        }
    return {"concepts": {"nouns": len(nouns()), "adjectives": len(adjectives()), "verbs": len(verbs())}, "by_language": table}


def translate(text: str, source: str, target: str | list[str] = "all") -> dict[str, Any]:
    if not text or not text.strip():
        raise LadderError("Enter text to translate.")
    if len(text) > 500:
        raise LadderError("The ladder translates single sentences of up to 500 characters.")
    src = language_id(source)
    if target == "all" or target == ["all"]:
        targets = [lang for lang in LADDER_ORDER if lang != src]
    else:
        targets = [language_id(t) for t in ([target] if isinstance(target, str) else target)]
    parsed = parse(text, src)
    frame = parsed["frame"]
    response: dict[str, Any] = {
        "ok": frame is not None,
        "source": text,
        "source_language": src,
        "targets": targets,
        "meaning": frame,
        "parse": {"unknown_words": parsed["unknown"], "notes": parsed["notes"], "ambiguities": parsed["ambiguities"],
                  "not_translated": parsed.get("dropped", [])},
        "accuracy_policy": ACCURACY_POLICY,
        "results": {},
    }
    if frame is None:
        response["message"] = (
            "The sentence could not be mapped to a meaning the ladder knows. It understands statements like "
            "'I trusted the truth', 'The king made a great house', 'The sun is great', 'I did not see the king', "
            "'Did the scribe write the name?', or single words from its "
            f"{len(nouns())}-noun, {len(verbs())}-verb concept lexicon."
        )
        return response
    if source in {"middle_egyptian", "old_egyptian"}:
        from ..translator import egyptian_to_modern
        formula = egyptian_to_modern(text, "english")
        if formula.get("formulae"):
            used = formula["formulae"]
            response["formulae"] = used
            response["parse"]["notes"].append("Contains a standard formula, read as a unit: " + "; ".join(
                f"{f['text']} = '{f['translation']}'" for f in used) + ". The word-by-word sentence below is a grammatical "
                "exercise and may not match the formula's idiomatic meaning.")
    left_out = [f"'{w}'" for w in dict.fromkeys(parsed["unknown"])] + parsed.get("dropped", [])
    # Never translate part of a sentence silently: say exactly what was left out.
    response["complete"] = not left_out
    if left_out:
        response["warning"] = ("Not translated: " + ", ".join(left_out) + ". The ladder translates one subject, verb and "
                               "object (or 'X is Y'), with negation and yes/no questions; the rest of the sentence was left out.")
        response["parse"]["notes"].append("Some words were not recognized and were left out of the meaning.")
    for lang in targets:
        response["results"][lang] = REALIZERS[lang].realize(frame)
    return response


def concept_table(concept: str) -> dict[str, Any]:
    """Every language's word for one concept (the dictionary view)."""
    for kind in ("noun", "adj", "verb"):
        frame = {"kind": "word", "word_kind": kind, "concept": concept}
        table = {"noun": nouns, "adj": adjectives, "verb": verbs}[kind]()
        if concept in table:
            return {"concept": concept, "kind": kind,
                    "results": {lang: REALIZERS[lang].realize(frame) for lang in LADDER_ORDER}}
    raise LadderError(f"Unknown concept '{concept}'.")
