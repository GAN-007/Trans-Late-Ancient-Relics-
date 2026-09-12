from __future__ import annotations

import re
import unicodedata
from typing import Any

# Familiar classroom readings for common teaching vocabulary. These are modern
# Egyptological conventions for accessibility and pedagogy, not recovered exact
# Middle Kingdom vocalizations.
KNOWN_READINGS = {
    "nfr": "nefer",
    "sḏm": "sedjem",
    "nṯr": "netjer",
    "ꜥnḫ": "ankh",
    "ḥtp": "hetep",
    "ḫpr": "kheper",
    "pr": "per",
    "rn": "ren",
    "kꜣ": "ka",
    "bꜣ": "ba",
    "mꜣꜥt": "maat",
    "nswt": "nesut",
    "ḏd": "djed",
    "rꜥ": "ra",
    "jnpw": "inpu",
}

UNIT_MAP = {
    "ꜣ": "a", "ꜥ": "a", "j": "i", "y": "y", "w": "w", "b": "b", "p": "p", "f": "f", "m": "m", "n": "n",
    "r": "r", "h": "h", "ḥ": "h", "ḫ": "kh", "ẖ": "kh", "z": "z", "s": "s", "š": "sh", "q": "q", "k": "k", "g": "g",
    "t": "t", "ṯ": "tj", "d": "d", "ḏ": "dj",
}
VOWELISH = {"ꜣ", "ꜥ", "j"}

# Broad consonantal IPA candidates. Several values changed through Egyptian's
# long history and some remain debated. The API therefore exposes per-symbol
# alternatives/notes rather than collapsing uncertainty into a single claim.
CONSONANTAL_IPA: dict[str, dict[str, Any]] = {
    "ꜣ": {"primary": "ʔ", "alternatives": [], "certainty": "low", "note": "Value changed historically; do not infer exact vocalization from this symbol alone."},
    "j": {"primary": "j", "alternatives": ["ʔ"], "certainty": "medium", "note": "Historical value and orthographic behavior vary."},
    "y": {"primary": "j", "alternatives": [], "certainty": "medium", "note": "Often treated as a glide/double reed value in transliteration."},
    "ꜥ": {"primary": "ʕ", "alternatives": [], "certainty": "medium", "note": "Broad traditional reconstruction; diachronic detail remains a research question."},
    "w": {"primary": "w", "alternatives": ["u"], "certainty": "medium", "note": "Consonantal/glide behavior can interact with later vocalization."},
    "b": {"primary": "b", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "p": {"primary": "p", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "f": {"primary": "f", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "m": {"primary": "m", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "n": {"primary": "n", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "r": {"primary": "r", "alternatives": ["ɾ"], "certainty": "medium", "note": "Exact rhotic realization is not directly encoded."},
    "h": {"primary": "h", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "ḥ": {"primary": "ħ", "alternatives": ["h"], "certainty": "medium", "note": "Traditional pharyngeal/fricative reconstruction; exact realization is debated."},
    "ḫ": {"primary": "x", "alternatives": ["χ"], "certainty": "medium", "note": "Broad velar/uvular fricative reconstruction."},
    "ẖ": {"primary": "ç", "alternatives": ["x"], "certainty": "medium", "note": "Conventionally differentiated from ḫ; historical realization varies."},
    "z": {"primary": "z", "alternatives": ["s"], "certainty": "medium", "note": "z/s contrast and spelling vary by period."},
    "s": {"primary": "s", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "š": {"primary": "ʃ", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "q": {"primary": "q", "alternatives": ["k"], "certainty": "medium", "note": "Broad uvular/velar reconstruction; diachronic variation matters."},
    "k": {"primary": "k", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "g": {"primary": "g", "alternatives": [], "certainty": "medium", "note": "Broad consonantal value; diachronic shifts occur."},
    "t": {"primary": "t", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "ṯ": {"primary": "c", "alternatives": ["tʃ"], "certainty": "medium", "note": "Often taught as tj/ch-like; historical palatal stop/affricate realization is period-sensitive."},
    "d": {"primary": "d", "alternatives": [], "certainty": "high", "note": "Broad consonantal value."},
    "ḏ": {"primary": "ɟ", "alternatives": ["dʒ"], "certainty": "medium", "note": "Often taught as dj/j-like; historical palatal realization is period-sensitive."},
}


def _word_reading(word: str) -> str:
    word = unicodedata.normalize("NFC", word.strip())
    bare = re.sub(r"[.=_\-]", "", word)
    if bare in KNOWN_READINGS:
        return KNOWN_READINGS[bare]
    units = [ch for ch in bare if ch in UNIT_MAP]
    if not units:
        return word
    out: list[str] = []
    for index, ch in enumerate(units):
        out.append(UNIT_MAP[ch])
        if index < len(units) - 1:
            next_ch = units[index + 1]
            if ch not in VOWELISH and next_ch not in VOWELISH:
                out.append("e")
    return "".join(out)


def _classroom_ipa(reading: str) -> str:
    # This transcribes the MODERN classroom reading, not Ancient Egyptian.
    text = reading.lower()
    replacements = [
        ("djed", "dʒed"), ("dj", "dʒ"), ("tj", "tʃ"), ("kh", "x"), ("sh", "ʃ"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def consonantal_skeleton(transliteration: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    ipa_parts: list[str] = []
    for char in unicodedata.normalize("NFC", transliteration):
        if char in CONSONANTAL_IPA:
            item = CONSONANTAL_IPA[char]
            symbols.append({"symbol": char, **item})
            ipa_parts.append(item["primary"])
        elif char.isspace():
            ipa_parts.append(" ")
        elif char in ".=_-()[]{}":
            continue
    return {
        "transliteration": transliteration,
        "ipa_skeleton": "".join(ipa_parts),
        "symbols": symbols,
        "certainty": "consonantal_only",
        "warning": "This is a broad consonantal reconstruction aid. It does not reconstruct unwritten vowels or guarantee a single historical pronunciation.",
    }


def classroom_reading(transliteration: str) -> dict[str, Any]:
    words = [w for w in re.split(r"\s+", transliteration.strip()) if w]
    reading = " ".join(_word_reading(w) for w in words)
    return {
        "transliteration": transliteration,
        "classroom_reading": reading,
        "classroom_ipa": _classroom_ipa(reading),
        "speech_language": "en",
        "certainty": "conventional",
        "warning": "This is a modern Egyptological classroom reading for accessibility and practice. Exact ancient Egyptian vowels and pronunciation are not fully recoverable from hieroglyphic spelling.",
    }


def pronunciation_analysis(transliteration: str, profile: str = "classroom") -> dict[str, Any]:
    profile = profile.strip().lower()
    if profile not in {"classroom", "consonantal", "research"}:
        raise ValueError("profile must be classroom, consonantal or research")
    classroom = classroom_reading(transliteration)
    skeleton = consonantal_skeleton(transliteration)
    result = {
        "profile": profile,
        "classroom": classroom,
        "consonantal": skeleton,
        "historical_vowels": {
            "reconstructed": False,
            "reason": "Hieroglyphic spelling normally omits vowels. Reliable lexical vocalization requires period-specific comparative evidence, especially Coptic and other Afroasiatic evidence, plus scholarly review.",
        },
    }
    if profile == "research":
        result["research_requirements"] = [
            "period/date of the text",
            "dialect/provenance when known",
            "lexeme identity and morphology",
            "Coptic descendants/cognates where relevant",
            "published phonological reconstruction with citation",
        ]
    return result
