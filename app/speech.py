from __future__ import annotations

import re
import unicodedata

# Familiar classroom readings for common teaching vocabulary. These are pedagogical
# conventions, not claims about exact Middle Kingdom vowels.
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


def classroom_reading(transliteration: str) -> dict:
    words = [w for w in re.split(r"\s+", transliteration.strip()) if w]
    reading = " ".join(_word_reading(w) for w in words)
    return {
        "transliteration": transliteration,
        "classroom_reading": reading,
        "speech_language": "en",
        "certainty": "conventional",
        "warning": "This is a modern Egyptological classroom reading for accessibility and practice. Exact ancient Egyptian vowels and pronunciation are not fully recoverable from hieroglyphic spelling.",
    }
