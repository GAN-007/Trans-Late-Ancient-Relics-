"""Native-script renderers for the Ancient Language Ladder.

Every glyph is produced from an official Unicode character *name*
(``unicodedata.lookup``) rather than from hand-typed code points, so a wrong
sign name fails loudly in tests instead of silently printing the wrong glyph.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# ---------------------------------------------------------------- cuneiform
SUMERIAN_AFFIX_SIGNS: dict[str, str] = {
    "mu": "MU", "e": "E", "un": "UN", "en": "EN", "de3": "NE", "ze2": "ZI",
    "eš": "ESH2", "ba": "BA", "i3": "NI", "ne": "NE", "še3": "ESH2", "ra": "RA",
    "a": "A", "me": "ME", "am3": "AN", "ĝu10": "MU", "bi2": "NE", "nu": "NU",
}


@lru_cache(maxsize=None)
def cuneiform_sign(name: str) -> str:
    return unicodedata.lookup("CUNEIFORM SIGN " + name)


def cuneiform(signs: list[str]) -> str:
    return "".join(cuneiform_sign(name) for name in signs)


# --------------------------------------------------------------- hieroglyphs
@lru_cache(maxsize=None)
def hieroglyph(gardiner: str) -> str:
    return unicodedata.lookup("EGYPTIAN HIEROGLYPH " + gardiner.upper())


def hieroglyphs(codes: list[str]) -> str:
    return "".join(hieroglyph(code) for code in codes)


EGYPTIAN_SUFFIX_GLYPHS: dict[str, list[str]] = {
    "j": ["A001"], "k": ["V031"], "ṯ": ["V013"], "f": ["I009"], "s": ["S029"],
    "n": ["N035", "Z002"], "ṯn": ["V013", "N035", "Z002"], "sn": ["S029", "N035", "Z002"],
}
EGYPTIAN_PERFECT_N = ["N035"]

# ------------------------------------------------------------------ Ethiopic
_ETH_CONS = {
    "ʾ": "GLOTTAL", "ʿ": "PHARYNGEAL", "h": "H", "l": "L", "ḥ": "HH", "m": "M",
    "ś": "SZ", "r": "R", "s": "S", "š": "SH", "q": "Q", "b": "B", "t": "T",
    "č": "C", "ḫ": "X", "n": "N", "ñ": "NY", "k": "K", "w": "W", "z": "Z",
    "ž": "ZH", "y": "Y", "d": "D", "ǧ": "J", "g": "G", "ṭ": "TH", "ṣ": "TS",
    "ḍ": "TZ", "f": "F", "p": "P",
}
_ETH_ORDER_GEEZ = {"a": "A", "u": "U", "i": "I", "ā": "AA", "e": "EE", "ə": "E", "o": "O", "": "E"}
_ETH_ORDER_AMHARIC = {"ä": "A", "u": "U", "i": "I", "a": "AA", "e": "EE", "ə": "E", "o": "O", "": "E"}
_LARYNGEALS = {"ʾ", "ʿ", "h", "ḥ", "ḫ"}
_ETH_VOWELS = set("aäuiāeəo")


@lru_cache(maxsize=None)
def _ethiopic_syllable(cons: str, order: str) -> str:
    base = _ETH_CONS[cons]
    sep = " " if base in {"GLOTTAL", "PHARYNGEAL"} else ""
    return unicodedata.lookup(f"ETHIOPIC SYLLABLE {base}{sep}{order}")


def ethiopic_word(translit: str, amharic: bool = False) -> str:
    """Convert one transliterated Ge'ez/Amharic word into fidel.

    Gemination is not written in fidel, so doubled consonants collapse.
    In Amharic, 'a' after a laryngeal is written with the first order (አ, ሀ).
    """
    text = unicodedata.normalize("NFC", translit.replace("-", "").replace("*", ""))
    orders = _ETH_ORDER_AMHARIC if amharic else _ETH_ORDER_GEEZ
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in _ETH_CONS:
            i += 1
            continue
        j = i + 1
        vowel = ""
        if j < len(text) and text[j] in _ETH_VOWELS:
            vowel = text[j]
            j += 1
        if not vowel and j < len(text) and text[j] == ch:
            # geminate: skip the first copy, the second carries the vowel
            i = j
            continue
        order = orders.get(vowel, "E")
        if amharic and vowel == "a" and ch in _LARYNGEALS:
            order = "A"
        out.append(_ethiopic_syllable(ch, order))
        i = j
    return "".join(out)


def ethiopic(words: list[str], amharic: bool = False) -> str:
    rendered = [ethiopic_word(w, amharic) for w in words if w.strip()]
    return "፡".join(rendered) + "።" if rendered else ""


# ----------------------------------------------------------------- Old Italic
_OLD_ITALIC = {
    "a": "A", "b": "BE", "c": "KE", "d": "DE", "e": "E", "f": "EF", "g": "KE", "h": "HE",
    "i": "I", "j": "I", "k": "KA", "l": "EL", "m": "EM", "n": "EN", "o": "O", "p": "PE",
    "q": "KU", "r": "ER", "s": "ES", "t": "TE", "u": "U", "v": "U", "x": "EKS", "z": "ZE",
}


def old_italic(text: str) -> str:
    out = []
    for word in text.split():
        letters = []
        for ch in unicodedata.normalize("NFD", word.lower()):
            name = _OLD_ITALIC.get(ch)
            if name:
                letters.append(unicodedata.lookup("OLD ITALIC LETTER " + name))
        out.append("".join(letters))
    return "·".join(w for w in out if w)


def latin_capitals(text: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return "·".join(stripped.upper().split())


# --------------------------------------------------------- Arabic + Safaitic
_ARABIC_LETTERS = {
    "b": "ب", "t": "ت", "ṯ": "ث", "j": "ج", "ḥ": "ح", "ḫ": "خ", "d": "د", "ḏ": "ذ",
    "r": "ر", "z": "ز", "s": "س", "š": "ش", "ṣ": "ص", "ḍ": "ض", "ṭ": "ط", "ẓ": "ظ",
    "ʿ": "ع", "ġ": "غ", "f": "ف", "q": "ق", "k": "ك", "l": "ل", "m": "م", "n": "ن",
    "h": "ه", "w": "و", "y": "ي",
}
_RASM = {
    "ب": "ٮ", "ت": "ٮ", "ث": "ٮ", "ن": "ٮ", "ي": "ٮ", "ج": "ح", "خ": "ح", "ذ": "د",
    "ز": "ر", "ش": "س", "ض": "ص", "ظ": "ط", "غ": "ع", "ف": "ڡ", "ق": "ٯ", "ة": "ه",
}
_RASM_FINAL = {"ن": "ں", "ي": "ى"}
_ARABIC_VOWELS = set("aiuāīū")
_SUN_LETTERS = set("tṯdḏrzsšṣḍṭẓln")


_ARABIC_PARTICLES = {"mā": "ما", "lā": "لا", "ʾa-mā": "أما", "ʾa-lā": "ألا"}


def _arabic_core(word: str, *, noun_feminine: bool, plural_verb: bool) -> str:
    """Consonantal Arabic spelling of one vocalized transliterated token."""
    w = unicodedata.normalize("NFC", word)
    if w in _ARABIC_PARTICLES:  # negatives are spelled with alif, not alif maqṣūra
        return _ARABIC_PARTICLES[w]
    prefix = ""
    for clitic in ("bi-", "li-", "wa-", "fa-"):
        if w.startswith(clitic):
            prefix += _ARABIC_LETTERS[clitic[0]]
            w = w[len(clitic):]
    article = False
    m = re.match(r"^(?:a?l-|a?([tṯdḏrzsšṣḍṭẓn])-(?=\1))", w)
    if m:
        article = True
        w = w[m.end():]
    # case/nunation endings are not written; keep alif for accusative -an
    tanwin_alif = bool(re.search(r"an$", w)) and not w.endswith("āan")
    w = re.sub(r"(un|in|an|u|i|a)$", "", w)
    full = w
    fem = noun_feminine and w.endswith("at")
    if fem:
        w = w[:-2]
    out: list[str] = []
    prev = ""
    for index, ch in enumerate(w):
        if ch == "ʾ":
            following = full[index + 1] if index + 1 < len(full) else ""
            if index == 0:
                out.append("ا")
            elif following == "a":
                out.append("أ")  # hamza on alif seat
            elif following == "u":
                out.append("ؤ")
            elif following == "i":
                out.append("ئ")
            else:
                out.append("ء")
            prev = ch
            continue
        if ch == "ā":
            if index == len(w) - 1 and index > 0 and w[index - 1] != "n":
                out.append("ى")  # final -ā of particles and weak verbs (ʿalā, raʾā)
            elif not (index == 1 and w[0] == "ʾ"):  # ʾā- is a single alif (madda)
                out.append("ا")
        elif ch == "ī":
            out.append("ي")
        elif ch == "ū":
            out.append("و")
        elif ch in _ARABIC_VOWELS:
            pass
        elif ch in _ARABIC_LETTERS:
            if ch == prev:  # shadda is not written
                continue
            out.append(_ARABIC_LETTERS[ch])
        prev = ch if ch not in _ARABIC_VOWELS else prev
    if fem:
        out.append("ة")
    elif tanwin_alif and out and out[-1] not in {"ا", "ة"}:
        out.append("ا")
    if plural_verb and out and out[-1] == "و":
        out.append("ا")
    return prefix + ("ال" if article else "") + "".join(out)


def arabic_dotted(tokens: list[dict]) -> str:
    return " ".join(_arabic_core(t["text"], noun_feminine=t.get("fem_noun", False), plural_verb=t.get("plural_verb", False)) for t in tokens)


def arabic_rasm(tokens: list[dict]) -> str:
    words = []
    for token in tokens:
        dotted = _arabic_core(token["text"], noun_feminine=token.get("fem_noun", False), plural_verb=token.get("plural_verb", False))
        dotted = dotted.replace("ء", "").replace("أ", "ا").replace("ؤ", "و").replace("ئ", "ي")
        chars = list(dotted)
        for i, ch in enumerate(chars):
            final = i == len(chars) - 1
            if final and ch in _RASM_FINAL:
                chars[i] = _RASM_FINAL[ch]
            elif ch in _RASM:
                chars[i] = _RASM[ch]
        words.append("".join(chars))
    return " ".join(words)


_ONA = {
    "h": "HEH", "l": "LAM", "ḥ": "HAH", "m": "MEEM", "q": "QAF", "w": "WAW", "š": "ES-2",
    "r": "REH", "b": "BEH", "t": "TEH", "s": "ES-1", "k": "KAF", "n": "NOON", "ḫ": "KHAH",
    "ṣ": "SAD", "f": "FEH", "ʾ": "ALEF", "ʿ": "AIN", "ḍ": "DAD", "j": "GEEM", "g": "GEEM",
    "d": "DAL", "ġ": "GHAIN", "ṭ": "TAH", "z": "ZAIN", "ḏ": "THAL", "y": "YEH", "ṯ": "THEH", "ẓ": "ZAH",
}


def safaitic(tokens: list[dict]) -> str:
    """Ancient North Arabian (Safaitic-style) consonantal rendering.

    Safaitic writes consonants only and uses the article h- where later
    Arabic has al-. Long vowels are not written.
    """
    words = []
    for token in tokens:
        w = unicodedata.normalize("NFC", token["text"])
        consonants = []
        clitic = re.match(r"^(bi|li|wa|fa)-", w)
        if clitic:
            consonants.append(clitic.group(1)[0])
            w = w[clitic.end():]
        m = re.match(r"^(?:a?l-|a?([tṯdḏrzsšṣḍṭẓn])-(?=\1))", w)
        if m:
            consonants.append("h")
            w = w[m.end():]
        w = re.sub(r"(un|in|an|u|i|a)$", "", w)
        if token.get("fem_noun") and w.endswith("at"):
            w = w[:-2] + "t"
        prev = ""
        for ch in w:
            if ch in _ONA and ch != prev:
                consonants.append(ch)
            prev = ch if ch not in _ARABIC_VOWELS else prev
        glyphs = "".join(unicodedata.lookup("OLD NORTH ARABIAN LETTER " + _ONA[c]) for c in consonants)
        if glyphs:
            words.append(glyphs)
    return " ".join(words)


def arabic_article(stem: str) -> str:
    """Vocalized definite article with sun-letter assimilation (al-šams -> aš-šams)."""
    first = stem[0]
    return f"a{first}-" if first in _SUN_LETTERS else "al-"


def arabic_article_elided(stem: str) -> str:
    first = stem[0]
    return f"{first}-" if first in _SUN_LETTERS else "l-"
