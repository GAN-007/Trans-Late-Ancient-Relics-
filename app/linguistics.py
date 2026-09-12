from __future__ import annotations

import re
import unicodedata

SUFFIX_PRONOUNS = {
    "j": {"english": "I / my", "swahili": "mimi / yangu", "person": "1sg"},
    "k": {"english": "you / your (m.sg)", "swahili": "wewe / yako (m.)", "person": "2sg.m"},
    "ṯ": {"english": "you / your (f.sg)", "swahili": "wewe / yako (f.)", "person": "2sg.f"},
    "f": {"english": "he / his", "swahili": "yeye / yake", "person": "3sg.m"},
    "s": {"english": "she / her", "swahili": "yeye / yake", "person": "3sg.f"},
    "n": {"english": "we / our", "swahili": "sisi / yetu", "person": "1pl"},
    "ṯn": {"english": "you / your (plural)", "swahili": "ninyi / yenu", "person": "2pl"},
    "sn": {"english": "they / their", "swahili": "wao / yao", "person": "3pl"},
}

PREPOSITIONS = {
    "m": {"english": ["in", "with", "as"], "swahili": ["katika", "na", "kama"]},
    "r": {"english": ["to", "toward", "concerning"], "swahili": ["kwa", "kuelekea", "kuhusu"]},
    "n": {"english": ["to", "for", "of"], "swahili": ["kwa", "ya"]},
    "ḥr": {"english": ["on", "upon", "because of"], "swahili": ["juu ya", "kwa sababu ya"]},
    "ẖr": {"english": ["under"], "swahili": ["chini ya"]},
    "ḫft": {"english": ["opposite", "against", "according to"], "swahili": ["mkabala na", "dhidi ya", "kulingana na"]},
}

CLASSROOM_OVERRIDES = {
    "nfr": "nefer",
    "sḏm": "sedjem",
    "nṯr": "netjer",
    "nṯrt": "netjeret",
    "ꜥnḫ": "ankh",
    "ḥtp": "hetep",
    "pr": "per",
    "rn": "ren",
    "jnk": "inek",
    "nswt": "nesut",
    "mꜣꜥt": "ma-at",
    "ḫpr": "kheper",
    "ḏd": "djed",
    "kꜣ": "ka",
    "bꜣ": "ba",
    "ꜣḫ": "akh",
}

CONSONANT_READINGS = {
    "ꜣ": "a",
    "ꜥ": "a",
    "j": "i",
    "y": "y",
    "w": "w",
    "b": "b",
    "p": "p",
    "f": "f",
    "m": "m",
    "n": "n",
    "r": "r",
    "h": "h",
    "ḥ": "h",
    "ḫ": "kh",
    "ẖ": "kh",
    "z": "z",
    "s": "s",
    "š": "sh",
    "q": "q",
    "k": "k",
    "g": "g",
    "t": "t",
    "ṯ": "ch",
    "d": "d",
    "ḏ": "j",
}


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text.strip().lower()))


def detect_intent(text: str, language: str) -> dict:
    q = _norm(text)
    rules = []
    if language == "english":
        rules = [
            ("greeting", r"\b(hello|hi|greetings|good morning|good evening)\b"),
            ("identity", r"\b(i am|my name is|who are you|who am i)\b"),
            ("question", r"\?|\b(what|who|where|when|why|how|which)\b"),
            ("request", r"\b(please|can you|could you|would you)\b"),
            ("command", r"^(go|come|give|take|listen|look|speak|write)\b"),
            ("location", r"\b(in|on|under|inside|outside|toward|to the)\b"),
            ("offering", r"\b(offering|bread|beer|incense|sacrifice)\b"),
            ("blessing", r"\b(life|prosperity|health|bless|peace)\b"),
        ]
    elif language == "swahili":
        rules = [
            ("greeting", r"\b(habari|jambo|salama|shikamoo|hujambo)\b"),
            ("identity", r"\b(mimi ni|jina langu|wewe ni nani)\b"),
            ("question", r"\?|\b(nini|nani|wapi|lini|kwa nini|vipi|gani)\b"),
            ("request", r"\b(tafadhali|naomba|unaweza)\b"),
            ("command", r"^(nenda|njoo|toa|chukua|sikiliza|angalia|sema|andika)\b"),
            ("location", r"\b(katika|juu|chini|ndani|nje|kuelekea)\b"),
            ("offering", r"\b(sadaka|mkate|bia|uvumba)\b"),
            ("blessing", r"\b(uhai|ustawi|afya|baraka|amani)\b"),
        ]
    matches = [name for name, pattern in rules if re.search(pattern, q, re.I)]
    if not matches:
        return {"primary": "statement", "signals": [], "confidence": 0.45}
    primary = "question" if "question" in matches else matches[0]
    return {"primary": primary, "signals": matches, "confidence": min(0.95, 0.62 + 0.08 * len(matches))}


def analyze_morphology(transliteration: str) -> dict:
    words = [w for w in re.split(r"\s+", unicodedata.normalize("NFC", transliteration.strip())) if w]
    analyses = []
    for word in words:
        item = {"surface": word, "stem": word, "suffix_pronoun": None, "preposition": None, "notes": []}
        if "." in word:
            stem, suffix = word.rsplit(".", 1)
            if suffix in SUFFIX_PRONOUNS:
                item["stem"] = stem
                item["suffix_pronoun"] = {"form": suffix, **SUFFIX_PRONOUNS[suffix]}
                item["notes"].append("Dot notation marks an attached suffix pronoun in this pedagogical analysis.")
        if item["stem"] in PREPOSITIONS:
            item["preposition"] = PREPOSITIONS[item["stem"]]
        analyses.append(item)
    return {"words": analyses, "word_count": len(words)}


def classroom_pronunciation(transliteration: str) -> dict:
    """Return an Egyptological classroom reading, never a claim about exact ancient vowels."""
    text = unicodedata.normalize("NFC", transliteration.strip())
    rendered_words = []
    for word in re.split(r"\s+", text):
        if not word:
            continue
        bare = word.replace(".", "-")
        if bare in CLASSROOM_OVERRIDES:
            rendered_words.append(CLASSROOM_OVERRIDES[bare])
            continue
        segments = []
        for ch in bare:
            if ch in "-=":
                segments.append("-")
            else:
                segments.append(CONSONANT_READINGS.get(ch, ch))
        raw = "".join(segments)
        # Insert a neutral e between simple adjacent consonants where no vowel-like reading exists.
        raw = re.sub(r"(?<=[bcdfghjklmnpqrstvwxyz])(?=[bcdfghjklmnpqrstvwxyz])", "e", raw, flags=re.I)
        rendered_words.append(raw)
    reading = " ".join(rendered_words)
    return {
        "transliteration": text,
        "classroom_reading": reading,
        "historical_accuracy": "conventional_not_reconstructed",
        "warning": "This is a modern Egyptological classroom reading for study and text-to-speech. Hieroglyphic Middle Egyptian usually omits vowels, so it is not the exact historical pronunciation.",
    }
