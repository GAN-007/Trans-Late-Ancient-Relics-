from __future__ import annotations

import re
from typing import Any

from .egyptian import current_lexicon

# Teaching-oriented Middle Egyptian morphology. These labels intentionally stay
# at the level that can be justified from transliteration alone; they do not
# pretend to resolve every verbal construction without sentence context.
SUFFIX_PRONOUNS = {
    "j": {"person": 1, "number": "singular", "gender": None, "english": "I/my/me", "swahili": "mimi/-angu"},
    "k": {"person": 2, "number": "singular", "gender": "masculine", "english": "you/your", "swahili": "wewe/-ako"},
    "ṯ": {"person": 2, "number": "singular", "gender": "feminine", "english": "you/your", "swahili": "wewe/-ako"},
    "f": {"person": 3, "number": "singular", "gender": "masculine", "english": "he/his/him", "swahili": "yeye/-ake"},
    "s": {"person": 3, "number": "singular", "gender": "feminine", "english": "she/her", "swahili": "yeye/-ake"},
    "n": {"person": 1, "number": "plural", "gender": None, "english": "we/our/us", "swahili": "sisi/-etu"},
    "ṯn": {"person": 2, "number": "plural", "gender": None, "english": "you/your (plural)", "swahili": "ninyi/-enu"},
    "sn": {"person": 3, "number": "plural", "gender": None, "english": "they/their/them", "swahili": "wao/-ao"},
}

INDEPENDENT_PRONOUNS = {"jnk", "ntk", "ntṯ", "ntf", "nts", "jnn", "ntṯn", "ntsn"}
PREPOSITIONS = {"m", "r", "n", "ḥr", "ẖr", "ḫft"}
NEGATIVES = {"n", "nn"}
COPULAR_OR_DEMONSTRATIVE = {"pw", "pn", "tn", "nn"}


def _lexicon_matches(base: str) -> list[dict[str, Any]]:
    q = base.lower()
    return [e for e in current_lexicon() if e.get("transliteration", "").lower() == q]


def analyze_word(token: str) -> dict[str, Any]:
    token = token.strip()
    segments = [segment for segment in token.split(".") if segment]
    base = segments[0] if segments else token
    suffixes = segments[1:]
    matches = _lexicon_matches(base)
    analyses: list[dict[str, Any]] = []

    if token in INDEPENDENT_PRONOUNS:
        analyses.append({"type": "independent_pronoun", "confidence": 0.95})
    if token in PREPOSITIONS:
        analyses.append({"type": "preposition", "confidence": 0.9})
    if token in NEGATIVES:
        analyses.append({"type": "negative_particle_candidate", "confidence": 0.75, "note": "Homography requires sentence context."})
    if token in COPULAR_OR_DEMONSTRATIVE:
        analyses.append({"type": "demonstrative_or_nominal_particle_candidate", "confidence": 0.75})

    suffix_analysis: list[dict[str, Any]] = []
    is_sdm_n_suffix_pattern = len(segments) >= 3 and segments[1] == "n" and segments[-1] in SUFFIX_PRONOUNS
    for index, suffix in enumerate(suffixes):
        if suffix == "n" and index == 0 and is_sdm_n_suffix_pattern:
            suffix_analysis.append({"surface": suffix, "type": "perfect_marker_candidate", "note": "In a verbal form such as sḏm.n.f, this n may mark the suffix-conjugation perfect; context and verb class matter."})
        elif suffix in SUFFIX_PRONOUNS:
            suffix_analysis.append({"surface": suffix, "type": "suffix_pronoun", **SUFFIX_PRONOUNS[suffix]})
        else:
            suffix_analysis.append({"surface": suffix, "type": "unresolved_suffix"})

    form_candidates: list[dict[str, Any]] = []
    if is_sdm_n_suffix_pattern:
        form_candidates.append(
            {
                "form": "sḏm.n.f-type",
                "confidence": 0.85,
                "subject": SUFFIX_PRONOUNS[segments[-1]],
                "warning": "This pattern label is morphological. Final tense/aspect translation still depends on syntax, discourse context and verb class.",
            }
        )
    elif len(segments) >= 2 and segments[-1] in SUFFIX_PRONOUNS:
        form_candidates.append(
            {
                "form": "suffix-pronoun construction",
                "confidence": 0.7,
                "subject_or_possessor": SUFFIX_PRONOUNS[segments[-1]],
                "warning": "A suffix pronoun can mark a verbal subject, possession, or a prepositional complement. Lexical category and clause context are required to choose.",
            }
        )

    return {
        "surface": token,
        "base": base,
        "segments": segments,
        "lexicon": [
            {
                "transliteration": e.get("transliteration"), "pos": e.get("pos"), "english": e.get("english", []),
                "swahili": e.get("swahili", []), "confidence": e.get("confidence"),
            }
            for e in matches
        ],
        "analyses": analyses,
        "suffixes": suffix_analysis,
        "form_candidates": form_candidates,
    }


def analyze_transliteration(text: str) -> dict[str, Any]:
    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    words = [analyze_word(token) for token in tokens]
    clause_hints: list[dict[str, Any]] = []

    if tokens and tokens[0] in INDEPENDENT_PRONOUNS:
        clause_hints.append({
            "type": "nominal_or_emphatic_clause_candidate", "confidence": 0.65,
            "evidence": f"Initial independent pronoun {tokens[0]}",
            "warning": "Independent pronouns participate in several constructions; this is not a complete syntactic parse.",
        })
    if tokens and tokens[0] in NEGATIVES:
        clause_hints.append({"type": "negative_construction_candidate", "confidence": 0.75, "evidence": f"Initial negative particle candidate {tokens[0]}"})
    if "pw" in tokens:
        clause_hints.append({
            "type": "pw-nominal-sentence_candidate", "confidence": 0.8, "evidence": "pw occurs in the clause",
            "warning": "Word order and information structure still need analysis.",
        })

    unresolved = [w["surface"] for w in words if not w["lexicon"] and not w["analyses"] and not w["form_candidates"]]
    return {
        "source": text,
        "tokens": tokens,
        "words": words,
        "clause_hints": clause_hints,
        "unresolved": unresolved,
        "method": "rule-based teaching morphology",
        "warning": "This analyzer exposes plausible morphology and ambiguity from transliteration. It is not yet a full period-aware Middle Egyptian morphological/syntactic parser.",
    }
