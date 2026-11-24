"""Coptic layer: script, transliteration, Sahidic pronunciation, dictionary reading and the
Egyptian -> Coptic bridge used for evidence-based vocalization.

Coptic (c. 3rd-11th c. CE) is the only stage of Egyptian written with vowels, so it is the
main evidence for how Egyptian words were pronounced. Dictionary data comes from the
Comprehensive Coptic Lexicon (CC BY-SA 4.0); pronunciation follows the reconstruction of
Sahidic in B. Layton, A Coptic Grammar (3rd ed. 2011), §§ 7-30.
"""
from __future__ import annotations

import gzip
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent / "data" / "coptic"
DIALECTS = {"S": "Sahidic", "B": "Bohairic", "A": "Akhmimic", "L": "Lycopolitan (Subakhmimic)", "M": "Mesokemic",
            "F": "Fayyumic", "Ak": "Old Akhmimic", "V": "Fayyumic variant (V)", "W": "Fayyumic variant (W)", "P": "Proto-Theban",
            "?": "unknown"}
STROKES = "̀̄̅̇̈︤︥︦⳯⳰⳱"
TRANSLIT = {"ⲁ": "a", "ⲃ": "b", "ⲅ": "g", "ⲇ": "d", "ⲉ": "e", "ⲍ": "z", "ⲏ": "ē", "ⲑ": "th", "ⲓ": "i", "ⲕ": "k", "ⲗ": "l",
            "ⲙ": "m", "ⲛ": "n", "ⲝ": "ks", "ⲟ": "o", "ⲡ": "p", "ⲣ": "r", "ⲥ": "s", "ⲧ": "t", "ⲩ": "u", "ⲫ": "ph", "ⲭ": "kh",
            "ⲯ": "ps", "ⲱ": "ō", "ϣ": "š", "ϥ": "f", "ϧ": "x", "ϩ": "h", "ϫ": "č", "ϭ": "ky", "ϯ": "ti", "ⳉ": "x"}
# (ipa, say, is_full_vowel); full vowels carry the word's stress, ⲉ is often reduced to ə
PHONES = {"ⲁ": ("a", "a", True), "ⲉ": ("ɛ", "e", False), "ⲏ": ("eː", "ay", True), "ⲓ": ("i", "ee", True), "ⲟ": ("o", "o", True),
          "ⲱ": ("oː", "oh", True), "ⲟⲩ": ("u", "oo", True), "ⲉⲓ": ("i", "ee", True),
          "ⲃ": ("β", "b", None), "ⲅ": ("g", "g", None), "ⲇ": ("d", "d", None), "ⲍ": ("z", "z", None), "ⲑ": ("tʰ", "t-h", None),
          "ⲕ": ("k", "k", None), "ⲗ": ("l", "l", None), "ⲙ": ("m", "m", None), "ⲛ": ("n", "n", None), "ⲝ": ("ks", "ks", None),
          "ⲡ": ("p", "p", None), "ⲣ": ("r", "r", None), "ⲥ": ("s", "s", None), "ⲧ": ("t", "t", None), "ⲫ": ("pʰ", "p-h", None),
          "ⲭ": ("kʰ", "k-h", None), "ⲯ": ("ps", "ps", None), "ϣ": ("ʃ", "sh", None), "ϥ": ("f", "f", None), "ϧ": ("x", "kh", None),
          "ϩ": ("h", "h", None), "ϫ": ("c", "ch", None), "ϭ": ("kʲ", "ky", None), "ϯ": ("ti", "tee", None), "ⳉ": ("x", "kh", None),
          "ⲩ": ("w", "w", None)}


def is_coptic(text: str) -> bool:
    return any(0x2C80 <= ord(c) <= 0x2CFF or 0x03E2 <= ord(c) <= 0x03EF for c in text)


def normalize(word: str) -> str:
    word = unicodedata.normalize("NFD", word.strip().lower())
    word = "".join(c for c in word if c not in STROKES and not unicodedata.combining(c))
    return unicodedata.normalize("NFC", word).replace("⸗", "").replace("=", "")


def transliterate(text: str) -> str:
    out = []
    for word in text.split():
        w = normalize(word).replace("ⲟⲩ", "ou")
        out.append("".join(TRANSLIT.get(c, c) for c in w))
    return " ".join(out)


def _segments(word: str) -> list[tuple[str, str, bool | None]]:
    w = normalize(word)
    segs: list[tuple[str, str, bool | None]] = []
    i = 0
    while i < len(w):
        two = w[i:i + 2]
        if i > 0 and w[i] == w[i - 1] and w[i] in "ⲁⲉⲏⲟⲱ" and segs and segs[-1][2]:
            segs.append(("ʔ", "’", None))  # doubled vowel = vowel + glottal stop (ⲙⲟⲟⲩ moʔw, ⲙⲁⲁⲩ maʔw)
            i += 1
            continue
        if two in ("ⲟⲩ", "ⲉⲓ"):
            nxt = w[i + 2:i + 3]
            prev_vowel = bool(segs) and segs[-1][2] is not None
            vowel_follows = nxt in "ⲁⲉⲏⲓⲟⲱ" and nxt != ""
            if two == "ⲟⲩ" and (prev_vowel or vowel_follows):
                segs.append(("w", "w", None))           # ⲟⲩ as consonant: ⲟⲩⲱⲙ
            elif two == "ⲉⲓ" and vowel_follows and not prev_vowel:
                segs.append(("j", "y", None))           # ⲉⲓ as consonant: ⲉⲓⲱⲧ
            else:
                segs.append(PHONES[two])
            i += 2
            continue
        char = w[i]
        if char == "ⲓ" and segs and segs[-1][2]:
            segs.append(("j", "y", None))  # ⲓ after a vowel is a glide: ⲥϩⲁⲓ shaj
        elif char in PHONES:
            segs.append(PHONES[char])
        i += 1
    return segs


def _syllables(segs: list[tuple[str, str, bool | None]]) -> list[list[tuple[str, str, bool | None]]]:
    """Split into syllables: one consonant before a vowel opens its syllable; ə nuclei count as vowels."""
    nuclei = [k for k, s in enumerate(segs) if s[2] is not None]
    if not nuclei:
        return [segs]
    out, start = [], 0
    for n, k in enumerate(nuclei):
        if n + 1 < len(nuclei):
            cluster = nuclei[n + 1] - k - 1
            end = k + 1 + max(0, cluster - 1)
            out.append(segs[start:end])
            start = end
        else:
            out.append(segs[start:])
    return out


def pronounce(text: str) -> dict[str, Any]:
    """Reconstructed Sahidic pronunciation: IPA and a read-aloud respelling with the stressed syllable in capitals."""
    ipa_words, say_words = [], []
    for word in text.split():
        segs = _segments(word)
        if not segs:
            continue
        full = [k for k, s in enumerate(segs) if s[2]]
        # ⲉ beside a full vowel is reduced to ə
        segs = [("ə", "e", False) if s[0] == "ɛ" and full and k not in full else s for k, s in enumerate(segs)]
        # unwritten ə: a final consonant cluster (ⲥⲱⲧⲙ sotəm, ⲱⲛϩ onəh) and an initial sonorant + consonant (ⲣⲣⲟ ərro)
        if len(segs) >= 2 and segs[-1][2] is None and segs[-2][2] is None and segs[-1][0] not in {"w", "j", "ʔ"}:
            segs.insert(len(segs) - 1, ("ə", "e", False))
        if len(segs) >= 2 and segs[0][2] is None and segs[1][2] is None and segs[0][0] in {"m", "n", "r", "l"}:
            segs.insert(0, ("ə", "e", False))
        syllables = _syllables(segs)
        stressed = max((n for n, syl in enumerate(syllables) if any(x[2] for x in syl)), default=None)
        ipa_parts, say_parts = [], []
        for n, syl in enumerate(syllables):
            ipa, say = "".join(x[0] for x in syl), "".join(x[1] for x in syl)
            if n == stressed and len(syllables) > 1:
                ipa, say = "ˈ" + ipa, say.upper()
            ipa_parts.append(ipa)
            say_parts.append(say)
        ipa_words.append(".".join(ipa_parts))
        say_words.append("-".join(say_parts))
    return {"ipa": "/" + " ".join(ipa_words) + "/", "say": " ".join(say_words), "system": "reconstructed",
            "note": "Sahidic as reconstructed by Layton, A Coptic Grammar §§ 7-30: ⲟⲩ is u or w, a doubled vowel adds a glottal stop, "
                    "an unwritten ə sits in final clusters; stress falls on the full vowel."}


# ------------------------------------------------------------------ dictionary
@lru_cache(maxsize=1)
def _lexicon() -> dict[str, Any]:
    with gzip.open(DATA / "ccl.json.gz", "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    by_form: dict[str, list[dict[str, Any]]] = {}
    for entry in data["entries"]:
        for form in entry["forms"]:
            by_form.setdefault(normalize(form["orth"]), []).append(entry)
    return {"meta": {k: data[k] for k in ("source", "license", "doi", "citation", "count")}, "by_form": by_form,
            "by_id": {e["id"]: e for e in data["entries"]}}


def lexicon_info() -> dict[str, Any]:
    return _lexicon()["meta"]


def _entry_view(entry: dict[str, Any]) -> dict[str, Any]:
    dialects: dict[str, list[str]] = {}
    for form in entry["forms"]:
        for d in form["dialects"] or ["?"]:
            dialects.setdefault(d, [])
            if form["orth"] not in dialects[d]:
                dialects[d].append(form["orth"])
    sahidic = (dialects.get("S") or next(iter(dialects.values()), [entry["forms"][0]["orth"]]))[0]
    return {"id": f"ccl:{entry['id']}", "tla_id": entry["id"], "lemma": sahidic, "transliteration": transliterate(sahidic),
            "pronunciation": pronounce(sahidic), "pos": entry["pos"], "gender": entry["gender"],
            "dialects": {DIALECTS.get(d, d): forms for d, forms in dialects.items()},
            "senses": entry["senses"], "etymology": entry["etym"]}


def lookup(word: str, limit: int = 5) -> list[dict[str, Any]]:
    entries = _lexicon()["by_form"].get(normalize(word), [])
    seen, out = set(), []
    for entry in entries:
        if entry["id"] not in seen:
            seen.add(entry["id"])
            out.append(_entry_view(entry))
    return out[:limit]


# Proclitics written together with the following word (Layton, A Coptic Grammar §§ 40-50, 334-345)
PREFIXES = {"ⲛⲧⲉ": "of (genitive)", "ⲡⲉ": "the (masc.)", "ⲧⲉ": "the (fem.)", "ⲛⲉ": "the (plural)", "ⲁϥ": "he (perfect: he did)",
            "ⲁⲥ": "she (perfect: she did)", "ⲁⲩ": "they (perfect: they did)", "ⲁⲓ": "I (perfect: I did)", "ⲁⲕ": "you m. (perfect)",
            "ϩⲛ": "in", "ϩⲙ": "in", "ⲟⲩ": "a, an (indefinite article)", "ⲡ": "the (masc.)", "ⲧ": "the (fem.)",
            "ⲛ": "the (plural) / of", "ⲙ": "of / the (plural)", "ⲉ": "to, toward", "ⲁ": "perfect conjugation"}


def read(text: str, learner: str = "en") -> dict[str, Any]:
    """Read Coptic text word by word: dictionary entry, dialect forms, pronunciation and gloss."""
    words = []
    for raw in re.findall(r"[Ⲁ-⳿Ϣ-ϯ̀-ͯ︤-︦⸗]+", text):
        entries = lookup(raw, 3)
        analysis = None
        if not entries:  # proclitic article / preposition / conjugation base written together with the word
            norm = normalize(raw)
            for prefix in sorted(PREFIXES, key=len, reverse=True):
                if norm.startswith(prefix) and len(norm) > len(prefix) + 1:
                    found = lookup(norm[len(prefix):], 3)
                    if found:
                        entries, analysis = found, {"prefix": prefix, "prefix_gloss": PREFIXES[prefix]}
                        break
        best = entries[0] if entries else None
        gloss = None
        if best and best["senses"]:
            gloss = best["senses"][0].get(learner) or best["senses"][0].get("en")
        words.append({"written": raw, "transliteration": transliterate(raw), "pronunciation": pronounce(raw),
                      "known": bool(best), "entry": best, "alternatives": entries[1:], "gloss": gloss, "analysis": analysis})
    return {"script": "coptic", "words": words, "known": sum(1 for w in words if w["known"]), "total": len(words),
            "source": lexicon_info()["citation"], "license": lexicon_info()["license"],
            "note": "Word-by-word dictionary reading; Coptic grammar (articles, conjugation bases, converters) is identified only when "
                    "written together with a dictionary word."}


# ------------------------------------------------------------------ Egyptian -> Coptic bridge
@lru_cache(maxsize=1)
def _etymologies() -> dict[str, Any]:
    raw = json.loads((DATA / "etymologies.json").read_text(encoding="utf-8"))
    resolved, unresolved = {}, []
    for pair in raw["pairs"]:
        match = next((e for e in _lexicon()["by_form"].get(normalize(pair["coptic"]), [])
                      if any(pair["match"] in s.get("en", "").lower() for s in e["senses"])), None)
        if match:
            resolved[pair["egyptian"]] = {**pair, "entry": match}
        else:
            unresolved.append(pair)
    return {"basis": raw["basis"], "resolved": resolved, "unresolved": unresolved}


def egyptian_key(translit: str) -> str:
    return unicodedata.normalize("NFC", translit.strip().lower()).replace("i", "j").replace("ı͗", "j").replace("ꞽ", "j")


def vocalization(egyptian: str) -> dict[str, Any] | None:
    """Coptic evidence for how an Egyptian word was pronounced: its attested descendant in every dialect."""
    data = _etymologies()
    pair = data["resolved"].get(egyptian_key(egyptian)) or data["resolved"].get(egyptian.strip())
    if not pair:
        return None
    view = _entry_view(pair["entry"])
    return {"egyptian": pair["egyptian"], "meaning": pair["meaning"], "confidence": pair["confidence"],
            "coptic": view, "basis": data["basis"],
            "note": "Coptic is the latest stage (c. 3rd-11th c. CE) and the only one written with vowels. Its forms show the "
                    "vowels and stress the word had by then; earlier pronunciation differed and is reconstructed from them, "
                    "together with cuneiform and Greek renderings of Egyptian names."}


def bridge_status() -> dict[str, Any]:
    data = _etymologies()
    return {"pairs": len(data["resolved"]), "unresolved": [p["egyptian"] for p in data["unresolved"]], "basis": data["basis"]}
