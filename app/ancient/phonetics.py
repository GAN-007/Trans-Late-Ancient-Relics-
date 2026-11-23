"""Pronunciation for every rung of the ladder: a scholarly IPA reading and a learner respelling.

Each language uses the pronunciation scholars actually teach, with its certainty stated:

* Old Akkadian, Proto-Semitic: reconstructed from comparative Semitic and cuneiform spellings
* Archaic Sumerian: approximate, known through Akkadian scribes' spellings; stress unknown
* Egyptian: the Egyptological classroom convention (vowels were never written); IPA shows consonants only
* Old Latin: restored pronunciation; Old Arabic: Classical Arabic; Ge'ez: traditional church reading
* Old Amharic, Swahili: the living pronunciation of the written forms

`say` is a respelling an English or Swahili speaker can read aloud (stressed syllable in capitals);
the guide's voice reads `say`, never the raw transliteration.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Phone:
    ipa: str
    say: str
    vowel: bool = False
    long: bool = False


def C(ipa: str, say: str | None = None) -> Phone:
    return Phone(ipa, ipa if say is None else say)


def V(ipa: str, say: str, long: bool = False) -> Phone:
    return Phone(ipa, say, True, long)


BASE_CONSONANTS = {c: C(c) for c in "bdfghklmnprstvz"}
BASE_CONSONANTS.update({
    "š": C("ʃ", "sh"), "ḫ": C("x", "kh"), "ʾ": C("ʔ", "’"), "ʔ": C("ʔ", "’"), "ʿ": C("ʕ", "’"), "ʕ": C("ʕ", "’"),
    "ḥ": C("ħ", "h"), "ġ": C("ɣ", "gh"), "ṯ": C("θ", "th"), "ḏ": C("ð", "dh"), "ẓ": C("ðˤ", "dh"), "ṣ": C("sˤ", "s"),
    "ḍ": C("dˤ", "d"), "ṭ": C("tˤ", "t"), "q": C("q", "k"), "j": C("d͡ʒ", "j"), "y": C("j", "y"), "w": C("w", "w"),
    "ś": C("ɬ", "s"), "č": C("t͡ʃ", "ch"), "ñ": C("ɲ", "ny"), "ž": C("ʒ", "zh"), "ĝ": C("ŋ", "ng"), "x": C("x", "kh"),
})
SEMITIC_VOWELS = {"a": V("a", "a"), "i": V("i", "i"), "u": V("u", "u"), "e": V("e", "e"), "o": V("o", "o"),
                  "ā": V("aː", "aa", True), "ī": V("iː", "ee", True), "ū": V("uː", "oo", True), "ē": V("eː", "ay", True),
                  "â": V("aː", "aa", True), "î": V("iː", "ee", True), "û": V("uː", "oo", True), "ê": V("eː", "ay", True)}
EMPHATIC_EJECTIVES = {"ṣ": C("sʼ", "s"), "ṭ": C("tʼ", "t"), "q": C("kʼ", "k")}

TABLES: dict[str, dict[str, Phone]] = {
    "old_akkadian": {**BASE_CONSONANTS, **EMPHATIC_EJECTIVES, **SEMITIC_VOWELS},
    "proto_semitic": {**BASE_CONSONANTS, **EMPHATIC_EJECTIVES, "ṣ́": C("ɬʼ", "tl"), **SEMITIC_VOWELS},
    "old_arabic": {**BASE_CONSONANTS, **SEMITIC_VOWELS},
    "archaic_sumerian": {**BASE_CONSONANTS, "a": V("a", "a"), "e": V("e", "e"), "i": V("i", "i"), "u": V("u", "u")},
    "geez": {**BASE_CONSONANTS, "ṣ": C("tsʼ", "ts"), "ḍ": C("tsʼ", "ts"), "ṭ": C("tʼ", "t"), "q": C("kʼ", "k"), "ś": C("s", "s"),
             "a": V("ə", "e"), "ā": V("a", "a"), "ə": V("ɨ", "i"), "i": V("i", "ee"), "u": V("u", "oo"), "e": V("e", "ay"), "o": V("o", "oh")},
    "old_amharic": {**BASE_CONSONANTS, "ṣ": C("tsʼ", "ts"), "ṭ": C("tʼ", "t"), "q": C("kʼ", "k"), "č̣": C("t͡ʃʼ", "ch"),
                    "ä": V("ə", "e"), "a": V("a", "a"), "ə": V("ɨ", "i"), "i": V("i", "ee"), "u": V("u", "oo"), "e": V("e", "ay"), "o": V("o", "oh")},
    "old_latin": {**BASE_CONSONANTS, "c": C("k"), "qu": C("kʷ", "kw"), "x": C("ks", "ks"), "h": C("h"), "y": C("j", "y"),
                  "ei": V("eː", "ay", True), "oi": V("oi", "oy", True), "ai": V("ai", "eye", True), "ou": V("oː", "oh", True),
                  "a": V("a", "a"), "e": V("e", "e"), "i": V("i", "i"), "o": V("o", "o"), "u": V("u", "oo")},
    "swahili": {**{c: C(c) for c in "bdfghklmnprstvz"}, "ch": C("t͡ʃ", "ch"), "sh": C("ʃ", "sh"), "ny": C("ɲ", "ny"),
                "ng'": C("ŋ", "ng"), "th": C("θ", "th"), "dh": C("ð", "dh"), "gh": C("ɣ", "gh"), "kh": C("x", "kh"),
                "j": C("ɟ", "j"), "y": C("j", "y"), "w": C("w"), "a": V("ɑ", "a"), "e": V("ɛ", "e"), "i": V("i", "ee"),
                "o": V("ɔ", "o"), "u": V("u", "oo")},
}

SYSTEMS = {
    "old_akkadian": ("reconstructed", "Reconstructed from comparative Semitic and the cuneiform spellings; the emphatic consonants "
                                      "(ṣ, ṭ, q) were probably glottalized. Stress falls on the last long or closed syllable."),
    "archaic_sumerian": ("approximate", "Sumerian sounds are known only through Akkadian scribes' spellings; ĝ was 'ng' and ḫ like Scottish 'loch'. "
                                        "Where the stress fell is unknown."),
    "old_latin": ("restored", "Restored pronunciation of Plautus' time: c is always k, u before a vowel is w. The archaic spelling does not "
                              "show vowel length, so long vowels and the stress are not marked (see the Classical Latin note)."),
    "old_arabic": ("classical", "Classical Arabic pronunciation, the standard reconstruction for pre-Islamic Arabic: ʿ and ḥ are made in "
                                "the throat, ṣ ḍ ṭ ẓ are 'heavy' (pharyngealized)."),
    "geez": ("traditional", "The traditional Ethiopian church pronunciation of Ge'ez; ṣ, ṭ and q are ejectives (said with a click-like "
                            "catch)."),
    "old_amharic": ("traditional", "Amharic pronunciation of the conservative written forms; ä sounds like the e in 'the'."),
    "proto_semitic": ("reconstructed", "Inferred by the comparative method; no one ever recorded these sounds."),
    "swahili": ("standard", "Standard Swahili; stress on the second-to-last syllable."),
    "old_egyptian": ("convention", "Egyptological classroom convention: Egyptian wrote no vowels, so an e is inserted between consonants. "
                                   "The IPA shows the consonants only; the true vowels are largely unknown."),
    "middle_egyptian": ("convention", "Egyptological classroom convention: Egyptian wrote no vowels, so an e is inserted between consonants. "
                                      "The IPA shows the consonants only; the true vowels are largely unknown."),
    "archaic_hieroglyphic": ("convention", "Egyptological classroom convention; the earliest writing records consonants only."),
    "proto_world": ("hypothetical", "Hypothetical roots; no real pronunciation can be reconstructed."),
}


def _phones(word: str, table: dict[str, Phone]) -> list[Phone]:
    keys = sorted(table, key=len, reverse=True)
    out: list[Phone] = []
    i = 0
    while i < len(word):
        for key in keys:
            if word.startswith(key, i):
                out.append(table[key])
                i += len(key)
                break
        else:
            i += 1  # punctuation, hyphens and sign indices carry no sound
    return out


def _latin_glides(word: str) -> str:
    # u and i before a vowel at the start of a syllable are the consonants w and j (uideo = wideo, iouos = jowos)
    word = re.sub(r"(?:^|(?<=[aeiou]))u(?=[aeiou])", "w", word)
    return re.sub(r"^i(?=[aeiou])", "y", word)


def _syllables(phones: list[Phone], open_syllables: bool = False) -> list[list[Phone]]:
    nuclei = [i for i, p in enumerate(phones) if p.vowel]
    if not nuclei:
        return [phones] if phones else []
    syllables: list[list[Phone]] = []
    start = 0
    for k, nucleus in enumerate(nuclei):
        if k + 1 < len(nuclei):
            nxt = nuclei[k + 1]
            cluster = nxt - nucleus - 1
            # one consonant goes to the next syllable; Bantu syllables are open (ku.bwa, ndi.zi), except in loans (mfal.me)
            end = nucleus + 1 + max(0, cluster - 1)
            if open_syllables and cluster >= 2:
                first, second = phones[nucleus + 1], phones[nucleus + 2]
                if first.ipa in {"n", "m"} or second.ipa in {"w", "j"}:
                    end = nucleus + 1
            syllables.append(phones[start:end])
            start = end
        else:
            syllables.append(phones[start:])
    return syllables


def _heavy(syllable: list[Phone]) -> bool:
    vowel_at = next(i for i, p in enumerate(syllable) if p.vowel)
    return syllable[vowel_at].long or vowel_at < len(syllable) - 1


def _stress(lang: str, syllables: list[list[Phone]], word: str) -> int | None:
    n = len(syllables)
    # Unknown or unpredictable from the spelling: Sumerian (unknown), Ge'ez/Amharic (not phonemic), Proto-Semitic (unknown),
    # Old Latin (the archaic spelling does not show vowel length, which decides Latin stress).
    if n <= 1 or lang in {"archaic_sumerian", "geez", "old_amharic", "proto_semitic", "old_latin"}:
        return None
    if lang == "swahili":
        return n - 2
    if lang == "old_latin":
        return n - 2 if n == 2 or _heavy(syllables[-2]) else n - 3
    if lang == "old_arabic":
        return n - 2 if _heavy(syllables[-2]) or n == 2 else n - 3
    if lang == "old_akkadian":
        if any(c in word for c in "âêîû") and any(p.long for p in syllables[-1] if p.vowel):
            return n - 1  # contracted final vowel carries the stress
        for index in range(n - 2, -1, -1):
            if _heavy(syllables[index]):
                return index
        return 0
    return None


def _word(lang: str, word: str) -> tuple[str, str]:
    table = TABLES[lang]
    w = unicodedata.normalize("NFC", word.lower()).replace("*", "")
    w = re.sub(r"[\d₀-₉?!.,;:]", "", w)
    if lang == "old_latin":
        w = _latin_glides(w)
    elif lang in {"archaic_sumerian", "old_akkadian", "old_arabic", "proto_semitic", "geez", "old_amharic"}:
        w = w.replace("-", "")
    phones = _phones(w, table)
    if lang == "swahili":
        # m before a consonant is a syllable of its own: m.to, m.fal.me, mwa.na.m.ke
        # but after a vowel, mb/mv is a prenasalized onset: nyu.mba
        phones = [Phone("m̩", "m", True) if p.ipa == "m" and i + 1 < len(phones) and not phones[i + 1].vowel
                  and phones[i + 1].ipa not in {"w", "j"}
                  and not (phones[i + 1].ipa in {"b", "v"} and i > 0 and phones[i - 1].vowel) else p for i, p in enumerate(phones)]
    syllables = _syllables(phones, open_syllables=lang == "swahili")
    stressed = _stress(lang, syllables, w)
    ipa_parts, say_parts = [], []
    for index, syllable in enumerate(syllables):
        ipa = "".join(p.ipa for p in syllable)
        say = "".join(p.say for p in syllable)
        if index == stressed and len(syllables) > 1:
            ipa, say = "ˈ" + ipa, say.upper()
        ipa_parts.append(ipa)
        say_parts.append(say)
    return ".".join(ipa_parts), "-".join(say_parts)


def _egyptian(text: str) -> tuple[str, str]:
    from ..avatar_chat.reading import egyptian_pronunciation
    from ..speech import consonantal_skeleton
    words = [w for w in re.split(r"\s+", text.replace("?", "")) if w]
    say = " ".join(egyptian_pronunciation(w.replace(".", "")) for w in words)
    ipa = " ".join(consonantal_skeleton(w)["ipa_skeleton"] for w in words)
    return ipa, say


def pronounce(lang: str, text: str) -> dict[str, Any] | None:
    """IPA and learner respelling for text written in a ladder language (None for English)."""
    text = (text or "").strip()
    if not text or lang == "english" or lang not in SYSTEMS:
        return None
    system, note = SYSTEMS[lang]
    if lang in {"old_egyptian", "middle_egyptian", "archaic_hieroglyphic"}:
        ipa, say = _egyptian(text)
    elif lang == "proto_world":
        words = [w.strip("*").lower() for w in text.split()]
        ipa, say = "", " ".join(words)
    else:
        words = [w for w in re.split(r"\s+", text) if w.strip("?*")]
        if lang == "old_arabic":
            # an elided article (l-, š-, …) is said with the previous word: ʿalā l-ḥaqqi -> ʿalāl-ḥaqqi
            joined: list[str] = []
            for w in words:
                m = re.match(r"^([^\W\d_aeiouāīū])-(?=\S)", w)
                if m and joined:
                    joined[-1] += m.group(1)
                    w = w[m.end():]
                joined.append(w)
            words = joined
        pairs = [_word(lang, w) for w in words]
        ipa = " ".join(p[0] for p in pairs if p[0])
        say = " ".join(p[1] for p in pairs if p[1])
    return {"ipa": f"/{ipa}/" if ipa else "", "say": say, "system": system, "note": note}


def speakable(lang: str, text: str) -> str:
    """What a voice should read aloud: the respelling for ancient languages, the text itself for living ones."""
    if lang in {"english", "swahili"}:
        return text
    p = pronounce(lang, text)
    return p["say"].lower() if p and p["say"] else text
