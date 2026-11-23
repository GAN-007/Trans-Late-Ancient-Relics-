"""Reading lessons: read ancient text the way a teacher reads a book aloud.

Given native-script text (pasted, or the signs a vision model saw), produce:
  - which script and language it is and which way it reads,
  - the whole meaning in the learner's language,
  - word-by-word segments: each sign, its sound value and its job, the
    transliteration, a pronunciation guide and the word's meaning,
  - spoken narration that walks through it in English or Swahili.

Readings are built from deterministic data first (Unicode sign names, the
Gardiner sign catalog, the Middle Egyptian lexicon and the ancient-language
ladder). A multimodal model's reading of a photo is cross-checked against the
same data and marked as confirmed or unverified, word by word.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from typing import Any

from ..ancient import scripts
from ..ancient.engine import LadderError, translate as ladder_translate
from ..ancient.grammar import REALIZERS
from ..ancient.lexicon import adjectives, nouns, verbs
from ..ancient.parsing import parse
from ..egyptian import current_lexicon, hieroglyphize_word, lookup_by_translit
from ..epigraphy import analyze_hieroglyphic_text

SCRIPTS = {
    "hieroglyphic": {"name": {"english": "Egyptian hieroglyphs", "swahili": "hieroglifu za Kimisri"}, "language": "middle_egyptian"},
    "cuneiform": {"name": {"english": "cuneiform", "swahili": "maandishi ya kikabari"}, "language": "archaic_sumerian"},
    "ethiopic": {"name": {"english": "Ge'ez script (fidel)", "swahili": "herufi za Ge'ez (fidel)"}, "language": "geez"},
    "old_italic": {"name": {"english": "Old Italic letters", "swahili": "herufi za Kiitaliki cha kale"}, "language": "old_latin"},
    "old_north_arabian": {"name": {"english": "Safaitic (Ancient North Arabian)", "swahili": "Safaitic (Kiarabu cha Kaskazini cha kale)"}, "language": "old_arabic"},
    "arabic": {"name": {"english": "Arabic script", "swahili": "herufi za Kiarabu"}, "language": "old_arabic"},
}

ROLE_LABELS = {
    "english": {
        "uniliteral": "sound sign for one consonant", "biliteral": "sound sign for two consonants",
        "triliteral": "sound sign for three consonants", "logogram": "word sign: it stands for the whole word",
        "determinative": "meaning marker: it shows the kind of word and is not read aloud",
        "complement": "helper sign: it repeats a sound of the sign before it", "syllable": "syllable",
        "letter": "letter", "logosyllable": "word or syllable sign", "unknown": "sign not in my catalog",
        "affix": "grammatical marker (case or verb ending)",
    },
    "swahili": {
        "uniliteral": "alama ya sauti ya konsonanti moja", "biliteral": "alama ya sauti ya konsonanti mbili",
        "triliteral": "alama ya sauti ya konsonanti tatu", "logogram": "alama ya neno zima",
        "determinative": "alama ya maana: inaonyesha aina ya neno na haisomwi kwa sauti",
        "complement": "alama saidizi: inarudia sauti ya alama iliyotangulia", "syllable": "silabi",
        "letter": "herufi", "logosyllable": "alama ya neno au silabi", "unknown": "alama isiyo kwenye orodha yangu",
        "affix": "alama ya kisarufi (kiambishi)",
    },
}


def _lang(language: str) -> str:
    return "swahili" if language == "swahili" else "english"


# ------------------------------------------------------------------ script detection
def char_script(char: str) -> str | None:
    name = unicodedata.name(char, "")
    if name.startswith("EGYPTIAN HIEROGLYPH"):
        return "hieroglyphic"
    if name.startswith("CUNEIFORM"):
        return "cuneiform"
    if name.startswith("ETHIOPIC"):
        return "ethiopic"
    if name.startswith("OLD ITALIC"):
        return "old_italic"
    if name.startswith("OLD NORTH ARABIAN"):
        return "old_north_arabian"
    if name.startswith("ARABIC"):
        return "arabic"
    return None


def detect_script(text: str) -> str | None:
    counts: dict[str, int] = {}
    for char in text:
        script = char_script(char)
        if script:
            counts[script] = counts.get(script, 0) + 1
    return max(counts, key=counts.get) if counts else None


def native_script_ratio(text: str) -> float:
    letters = [c for c in text if not c.isspace() and unicodedata.category(c)[0] in {"L", "S", "N"}]
    if not letters:
        return 0.0
    return sum(1 for c in letters if char_script(c)) / len(letters)


# ------------------------------------------------------------------ pronunciation
_EGY_SOUNDS = {
    "ꜣ": ("a", True), "j": ("i", True), "y": ("y", False), "ꜥ": ("a", True), "w": ("w", False),
    "b": ("b", False), "p": ("p", False), "f": ("f", False), "m": ("m", False), "n": ("n", False),
    "r": ("r", False), "h": ("h", False), "ḥ": ("h", False), "ḫ": ("kh", False), "ẖ": ("kh", False),
    "s": ("s", False), "z": ("s", False), "š": ("sh", False), "q": ("k", False), "ḳ": ("k", False),
    "k": ("k", False), "g": ("g", False), "t": ("t", False), "ṯ": ("tj", False), "d": ("d", False), "ḏ": ("dj", False),
}


def egyptian_pronunciation(translit: str) -> str:
    """Egyptological teaching pronunciation: weak consonants read as vowels, 'e' between other consonants.

    nfr -> nefer, ꜥnḫ -> ankh, ḥtp -> hetep, mꜣꜥt -> maat, nṯr -> netjer.
    This is a modern classroom convention, not the ancient sound.
    """
    word = unicodedata.normalize("NFC", translit.lower())
    word = re.sub(r"[.\-=:⸗]", "", word)
    sounds: list[tuple[str, bool]] = []
    for char in word:
        if char in _EGY_SOUNDS:
            sounds.append(_EGY_SOUNDS[char])
        elif char.isalpha():
            sounds.append((char, char in "aeiou"))
    if word in PRONUNCIATION_EXCEPTIONS:
        return PRONUNCIATION_EXCEPTIONS[word]
    resolved: list[tuple[str, bool]] = []
    for index, (sound, vowel) in enumerate(sounds):
        if sound == "w":
            prev_vowel = index > 0 and sounds[index - 1][1]
            next_vowel = index + 1 < len(sounds) and sounds[index + 1][1]
            if not prev_vowel and not next_vowel:
                sound, vowel = "u", True
        resolved.append((sound, vowel))
    out = ""
    for index, (sound, vowel) in enumerate(resolved):
        prev = resolved[index - 1] if index else None
        before_prev = resolved[index - 2] if index > 1 else None
        final_cluster = index == len(resolved) - 1 and before_prev is not None and before_prev[1]
        if prev and not prev[1] and not vowel and not final_cluster:
            out += "e"
        out += sound
    return out


PRONUNCIATION_EXCEPTIONS = {"ptḥ": "ptah", "jmn": "amun", "wsjr": "usir", "ꜣst": "aset", "ḥr": "heru", "jnpw": "anpu", "ḏḥwtj": "djehuti"}


# ------------------------------------------------------------------ word indexes
def _ladder_rows(kind: str, table: dict[str, Any], code: str, script_fn) -> list[dict[str, Any]]:
    rows = []
    for concept, item in table.items():
        entry = item.get(code)
        if not entry:
            continue
        try:
            glyphs = script_fn(entry)
        except (KeyError, ValueError, TypeError):
            continue
        if not glyphs:
            continue
        english = item["en"][0] if isinstance(item["en"], list) else item["en"]["base"]
        sw = item["sw"]
        swahili = sw["f"] if isinstance(sw, dict) and "f" in sw else ("ku" + sw["root"] if isinstance(sw, dict) else sw)
        translit = entry.get("f") or entry.get("perf") or entry.get("root") or ""
        rows.append({"glyphs": glyphs, "transliteration": translit, "english": english, "swahili": swahili,
                     "kind": kind, "concept": concept, "source": "ancient ladder lexicon", "confidence": entry.get("c", "high")})
    return rows


@lru_cache(maxsize=1)
def hieroglyph_words() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}

    def add(row: dict[str, Any], priority: int) -> None:
        key = row["glyphs"]
        if key and (key not in index or index[key]["_priority"] < priority):
            index[key] = {**row, "_priority": priority}

    for entry in current_lexicon():
        english = (entry.get("english") or [""])[0]
        swahili = (entry.get("swahili") or [""])[0]
        base = {"transliteration": entry["transliteration"], "english": english, "swahili": swahili,
                "kind": entry.get("pos", ""), "source": "Middle Egyptian lexicon", "confidence": entry.get("confidence", "medium")}
        if entry.get("hieroglyphs"):
            add({**base, "glyphs": entry["hieroglyphs"]}, 3)
        spelled = hieroglyphize_word(entry["transliteration"]).get("hieroglyphs", "")
        if spelled and not any(c == "?" for c in spelled):
            add({**base, "glyphs": spelled, "source": "Middle Egyptian lexicon (phonetic spelling)"}, 1)
    for row in _ladder_rows("noun", nouns(), "egy", lambda e: scripts.hieroglyphs(e["gl"]) if e.get("gl") else ""):
        add(row, 2)
    for row in _ladder_rows("adj", adjectives(), "egy", lambda e: scripts.hieroglyphs(e["gl"]) if e.get("gl") else ""):
        add(row, 2)
    for row in _ladder_rows("verb", verbs(), "egy", lambda e: scripts.hieroglyphs(e["gl"]) if e.get("gl") else ""):
        add(row, 2)
    return index


@lru_cache(maxsize=1)
def cuneiform_words() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for table, kind in ((nouns(), "noun"), (adjectives(), "adj"), (verbs(), "verb")):
        def render(entry: dict[str, Any]) -> str:
            return scripts.cuneiform(entry.get("pre_signs", []) + entry["signs"]) if entry.get("signs") else ""
        for row in _ladder_rows(kind, table, "sux", render):
            if row["glyphs"] not in index:
                sux = table[row["concept"]]["sux"]
                row["transliteration"] = (sux.get("pre", "") + " " + sux.get("root", sux.get("f", ""))).strip() if kind == "verb" else sux["f"]
                index[row["glyphs"]] = row
    return index


TOKEN_LANGS = {"hieroglyphic": ["old_egyptian", "middle_egyptian"], "cuneiform": ["archaic_sumerian"],
               "ethiopic": ["geez", "old_amharic"], "old_italic": ["old_latin"], "old_north_arabian": ["old_arabic"], "arabic": ["old_arabic"]}


@lru_cache(maxsize=None)
def token_lexicon(lang: str) -> dict[str, tuple[str, dict[str, Any]]]:
    """Every native-script word the ladder can write in `lang` -> (transliteration, token info)."""
    from ..ancient.parsing import _exact_key, _synthetic_frames
    realizer = REALIZERS[lang]
    index: dict[str, tuple[str, dict[str, Any]]] = {}
    for frame in _synthetic_frames(lang):
        try:
            realizer._refusal = None
            tokens = realizer.tokens_for(frame)
        except (KeyError, TypeError):
            continue
        for token in tokens:
            if token.is_gap or not token.text:
                continue
            try:
                renderings = realizer.render_scripts([token]).values()
            except (KeyError, ValueError):
                continue
            for rendering in renderings:
                key = _exact_key(rendering)
                if key and " " not in key and key not in index:
                    index[key] = (token.text, dict(token.info))
    return index


def gloss_info(info: dict[str, Any]) -> dict[str, str]:
    """English and Swahili gloss for one ladder token."""
    kind = info.get("type")
    if kind == "noun":
        item = nouns().get(info.get("concept"), {})
        return {"english": item.get("en", [""])[0], "swahili": item.get("sw", {}).get("f", "")}
    if kind == "adj":
        item = adjectives().get(info.get("concept"), {})
        return {"english": item.get("en", [""])[0], "swahili": "-" + item.get("sw", "")}
    if kind == "verb" and info.get("person"):
        frame = {"kind": "clause", "subject": {"person": info["person"]}, "verb": info["verb"], "tense": info["tense"], "object": None}
        return {"english": REALIZERS["english"].realize(frame)["text"], "swahili": REALIZERS["swahili"].realize(frame)["text"]}
    if kind == "verb":
        item = verbs().get(info.get("verb"), {})
        return {"english": "to " + item.get("en", {}).get("base", ""), "swahili": "ku" + item.get("sw", {}).get("root", "")}
    if kind == "pron":
        frame = {"kind": "identity", "subject": {"person": info["person"]}, "predicate": {"noun": "king", "adj": None}}
        return {"english": REALIZERS["english"].realize(frame)["tokens"][0]["text"], "swahili": REALIZERS["swahili"].realize(frame)["tokens"][0]["text"]}
    if kind == "cop":
        return {"english": "(is / am / are)", "swahili": "ni"}
    if kind == "prep":
        return {"english": "(preposition: in, to, on)", "swahili": "(kihusishi: katika, kwa)"}
    if kind == "idiom":
        return {"english": "the heart (in 'fill the heart' = trust)", "swahili": "moyo (katika 'kujaza moyo' = kuamini)"}
    return {"english": "", "swahili": ""}


def _longest_match(chars: list[str], start: int, index: dict[str, Any], max_len: int = 8) -> tuple[int, dict[str, Any] | None]:
    for length in range(min(max_len, len(chars) - start), 0, -1):
        key = "".join(chars[start:start + length])
        if key in index:
            return length, index[key]
    return 0, None


# ------------------------------------------------------------------ hieroglyphic reader
def gardiner_from_unicode(glyph: str) -> str | None:
    """EGYPTIAN HIEROGLYPH V022 -> V22 (also for signs outside the teaching catalog)."""
    name = unicodedata.name(glyph, "")
    m = re.match(r"EGYPTIAN HIEROGLYPH ([A-Z]+)0*(\d+)([A-Z]?)$", name)
    if not m:
        return None
    prefix = m.group(1).capitalize() if len(m.group(1)) == 2 else m.group(1)
    return f"{prefix}{int(m.group(2))}{m.group(3).lower()}"


def _sign_role(info: dict[str, Any]) -> str:
    functions = set(info.get("possible_functions") or [])
    for role in ("triliteral", "biliteral", "uniliteral"):
        if role in functions:
            return role
    if "logogram" in functions:
        return "logogram"
    if "determinative" in functions:
        return "determinative"
    return "unknown"


def _consonants(value: str) -> list[str]:
    return [c for c in unicodedata.normalize("NFC", value) if c.isalpha() or c in "ꜣꜥ"]


def _gloss_translit(translit: str) -> dict[str, Any] | None:
    hits = lookup_by_translit(translit)
    if hits:
        entry = hits[0]
        return {"english": (entry.get("english") or [""])[0], "swahili": (entry.get("swahili") or [""])[0],
                "source": "Middle Egyptian lexicon", "confidence": entry.get("confidence", "medium")}
    for item in nouns().values():
        egy = item.get("egy")
        if egy and egy.get("f") == translit:
            return {"english": item["en"][0], "swahili": item["sw"]["f"], "source": "ancient ladder lexicon", "confidence": egy.get("c", "high")}
    return None


def read_hieroglyphs(text: str, language: str) -> dict[str, Any]:
    lang = _lang(language)
    analysis = analyze_hieroglyphic_text(text)
    signs = [s for s in analysis["signs"]]
    chars = [s["glyph"] for s in signs]
    words = hieroglyph_words()
    segments: list[dict[str, Any]] = []
    i = 0
    while i < len(signs):
        length, match = _longest_match(chars, i, words)
        group = signs[i:i + (length or 1)]
        sign_rows = []
        for position, sign in enumerate(group):
            info = sign.get("sign") or {}
            role = _sign_role(info) if sign["known"] else "unknown"
            values = info.get("values") or []
            if match and position > 0 and role == "uniliteral" and values and len(group) > 1:
                first_values = (group[0].get("sign") or {}).get("values") or [""]
                if values[0] in _consonants(first_values[0]) and len(_consonants(first_values[0])) > 1:
                    role = "complement"
            sign_rows.append({"glyph": sign["glyph"], "code": info.get("gardiner") or gardiner_from_unicode(sign["glyph"]), "value": values[0] if values else None,
                              "values": values, "role": role, "role_label": ROLE_LABELS[lang][role],
                              "note": info.get("note")})
        if match:
            translit = match["transliteration"]
            needed = _consonants(translit)
            j = i + length
            while len(needed) > 1 and j < len(signs):
                info = signs[j].get("sign") or {}
                values = info.get("values") or []
                if _sign_role(info) == "uniliteral" and values and values[0] in needed and not _starts_word(chars, j, words):
                    sign_rows.append({"glyph": signs[j]["glyph"], "code": info.get("gardiner"), "value": values[0], "values": values,
                                      "role": "complement", "role_label": ROLE_LABELS[lang]["complement"], "note": info.get("note")})
                    j += 1
                else:
                    break
            length = j - i
            segment = {"original": "".join(chars[i:i + length]), "signs": sign_rows, "transliteration": translit,
                       "pronunciation": egyptian_pronunciation(translit),
                       "meaning": {"english": match["english"], "swahili": match["swahili"]},
                       "source": match["source"], "status": "confirmed", "confidence": match["confidence"]}
            i += length
        else:
            segment = _group_unmatched(signs, i, lang)
            i += len(segment["signs"])
        segments.append(segment)
    _attach_determinatives(segments, lang)
    return {
        "script": "hieroglyphic", "language": "middle_egyptian", "segments": segments,
        "direction": "as_written",
        "unknown_signs": [s["glyph"] for s in analysis["unknown_signs"]],
    }


def _starts_word(chars: list[str], start: int, index: dict[str, Any]) -> bool:
    """True if a multi-sign dictionary word begins here (so the sign is not a complement)."""
    length, _match = _longest_match(chars, start, index)
    return length > 1


def _group_unmatched(signs: list[dict[str, Any]], start: int, lang: str) -> dict[str, Any]:
    """A multiliteral sign plus the complements that repeat its sounds form one word."""
    first = signs[start]
    info = first.get("sign") or {}
    values = info.get("values") or []
    role = _sign_role(info) if first["known"] else "unknown"
    rows = [{"glyph": first["glyph"], "code": info.get("gardiner") or gardiner_from_unicode(first["glyph"]), "value": values[0] if values else None, "values": values,
             "role": role, "role_label": ROLE_LABELS[lang][role], "note": info.get("note")}]
    translit = values[0] if values else ""
    if values and len(_consonants(values[0])) > 1:
        needed = _consonants(values[0])
        j = start + 1
        while j < len(signs):
            nxt = signs[j].get("sign") or {}
            nxt_values = nxt.get("values") or []
            if _sign_role(nxt) == "uniliteral" and nxt_values and nxt_values[0] in needed:
                rows.append({"glyph": signs[j]["glyph"], "code": nxt.get("gardiner"), "value": nxt_values[0], "values": nxt_values,
                             "role": "complement", "role_label": ROLE_LABELS[lang]["complement"], "note": nxt.get("note")})
                j += 1
            else:
                break
    gloss = _gloss_translit(translit) if translit else None
    return {"original": "".join(r["glyph"] for r in rows), "signs": rows, "transliteration": translit,
            "pronunciation": egyptian_pronunciation(translit) if translit else "",
            "meaning": {"english": gloss["english"], "swahili": gloss["swahili"]} if gloss else {"english": "", "swahili": ""},
            "source": gloss["source"] if gloss else "sign catalog", "status": "confirmed" if gloss else "sign_only",
            "confidence": gloss["confidence"] if gloss else "low"}


def _attach_determinatives(segments: list[dict[str, Any]], lang: str) -> None:
    """A lone determinative after a word belongs to that word and is not pronounced."""
    merged: list[dict[str, Any]] = []
    for segment in segments:
        only = segment["signs"][0] if len(segment["signs"]) == 1 else None
        if only and only["role"] == "determinative" and segment["status"] == "sign_only" and merged:
            merged[-1]["signs"].append(only)
            merged[-1]["original"] += only["glyph"]
            continue
        merged.append(segment)
    segments[:] = merged


# ------------------------------------------------------------------ cuneiform reader
AFFIX_SIGN_NAMES = set(scripts.SUMERIAN_AFFIX_SIGNS.values()) - {"A", "MU"}


def cuneiform_reading(char: str) -> str:
    name = unicodedata.name(char, "").replace("CUNEIFORM SIGN ", "").replace("CUNEIFORM ", "")
    reading = name.lower().replace(" times ", "×").replace(" plus ", "+").replace(" ", "-")
    return reading.replace("sh", "š").replace("szu", "šu")


def read_cuneiform(text: str, language: str) -> dict[str, Any]:
    lang = _lang(language)
    chars = [c for c in text if char_script(c) == "cuneiform" and not unicodedata.name(c, "").startswith("CUNEIFORM PUNCTUATION")]
    words = cuneiform_words()
    segments = []
    i = 0
    while i < len(chars):
        length, match = _longest_match(chars, i, words)
        group = chars[i:i + (length or 1)]
        signs = [{"glyph": c, "code": unicodedata.name(c, "").replace("CUNEIFORM SIGN ", ""), "value": cuneiform_reading(c),
                  "values": [cuneiform_reading(c)], "role": "logosyllable", "role_label": ROLE_LABELS[lang]["logosyllable"]} for c in group]
        if match:
            segments.append({"original": "".join(group), "signs": signs, "transliteration": match["transliteration"],
                             "pronunciation": re.sub(r"\d", "", match["transliteration"]).replace("ĝ", "ng").replace("š", "sh"),
                             "meaning": {"english": match["english"], "swahili": match["swahili"]},
                             "source": match["source"], "status": "confirmed", "confidence": match["confidence"]})
            i += length
        else:
            reading = signs[0]["value"]
            affix = signs[0]["code"] in AFFIX_SIGN_NAMES and segments and segments[-1]["status"] == "confirmed"
            if affix:
                signs[0]["role"], signs[0]["role_label"] = "affix", ROLE_LABELS[lang]["affix"]
                segments[-1]["signs"].append(signs[0])
                segments[-1]["original"] += group[0]
                i += 1
                continue
            segments.append({"original": group[0], "signs": signs, "transliteration": reading,
                             "pronunciation": re.sub(r"\d", "", reading).replace("š", "sh"),
                             "meaning": {"english": "", "swahili": ""}, "source": "Unicode sign name", "status": "sign_only", "confidence": "low"})
            i += 1
    return {"script": "cuneiform", "language": "archaic_sumerian", "segments": segments, "direction": "left_to_right"}


# ------------------------------------------------------------------ alphabetic / syllabic readers
_ETH_REVERSE = {v: k for k, v in scripts._ETH_CONS.items()}
_ETH_VOWEL = {"geez": {"A": "a", "U": "u", "I": "i", "AA": "ā", "EE": "e", "E": "ə", "O": "o", "WAA": "wā", "WA": "wa"},
              "amharic": {"A": "ä", "U": "u", "I": "i", "AA": "a", "EE": "e", "E": "ə", "O": "o", "WAA": "wa", "WA": "wä"}}


def ethiopic_syllable(char: str, amharic: bool = False) -> str:
    name = unicodedata.name(char, "")
    if not name.startswith("ETHIOPIC SYLLABLE "):
        return ""
    rest = name[len("ETHIOPIC SYLLABLE "):]
    if rest.startswith(("GLOTTAL ", "PHARYNGEAL ")):
        base, order = rest.split(" ", 1)
    else:
        base, order = None, None
        for cons in sorted(_ETH_REVERSE, key=len, reverse=True):
            if rest.startswith(cons) and rest[len(cons):] in _ETH_VOWEL["geez"]:
                base, order = cons, rest[len(cons):]
                break
        if base is None:
            return rest.lower()
    consonant = _ETH_REVERSE.get(base, base.lower())
    vowel = _ETH_VOWEL["amharic" if amharic else "geez"].get(order, "")
    return consonant + vowel


_OLD_ITALIC_SOUND = {unicodedata.lookup("OLD ITALIC LETTER " + name): latin for latin, name in scripts._OLD_ITALIC.items() if latin not in "jvg"}
_OLD_ITALIC_SOUND[unicodedata.lookup("OLD ITALIC LETTER KE")] = "c"
_ARABIC_SOUND = {letter: translit for translit, letter in scripts._ARABIC_LETTERS.items()}
_ARABIC_SOUND.update({"ا": "ā / ʾ", "أ": "ʾa", "إ": "ʾi", "ء": "ʾ", "ى": "ā", "ة": "-a(t)", "ؤ": "ʾu", "ئ": "ʾi", "آ": "ʾā"})
_ONA_SOUND = {unicodedata.lookup("OLD NORTH ARABIAN LETTER " + name): translit for translit, name in scripts._ONA.items() if translit != "g"}


def letter_sound(char: str, script: str) -> str:
    if script == "old_italic":
        return _OLD_ITALIC_SOUND.get(char, char)
    if script == "arabic":
        return _ARABIC_SOUND.get(char, char)
    if script == "old_north_arabian":
        return _ONA_SOUND.get(char, char)
    return char


def _word_meaning(word: str, languages: list[str]) -> tuple[str | None, dict[str, Any] | None]:
    for lang in languages:
        parsed = parse(word, lang)
        frame = parsed.get("frame")
        if frame and not parsed["unknown"]:
            return lang, frame
    return None, None


def _frame_gloss(frame: dict[str, Any]) -> dict[str, str]:
    return {"english": REALIZERS["english"].realize(frame)["text"], "swahili": REALIZERS["swahili"].realize(frame)["text"]}


def read_alphabetic(text: str, script: str, language: str) -> dict[str, Any]:
    lang = _lang(language)
    separators = r"[\s፡።·,]+"
    raw_words = [w for w in re.split(separators, unicodedata.normalize("NFC", text)) if w and any(char_script(c) for c in w)]
    candidates = {"ethiopic": ["geez", "old_amharic"], "old_italic": ["old_latin"], "old_north_arabian": ["old_arabic"], "arabic": ["old_arabic"]}[script]
    segments = []
    detected_lang = candidates[0]
    for word in raw_words:
        letters = []
        for char in word:
            if script == "ethiopic":
                value = ethiopic_syllable(char)
                role = "syllable"
            else:
                value = letter_sound(char, script)
                role = "letter"
            letters.append({"glyph": char, "code": unicodedata.name(char, ""), "value": value, "values": [value], "role": role,
                            "role_label": ROLE_LABELS[lang][role]})
        found_lang, frame = _word_meaning(word, candidates)
        if found_lang:
            detected_lang = found_lang
        translit = ""
        if script == "ethiopic":
            translit = "".join(ethiopic_syllable(c, amharic=found_lang == "old_amharic") for c in word)
        elif frame:
            translit = REALIZERS[found_lang].realize(frame)["text"]
        else:
            translit = "".join(l["value"].split(" ")[0].lstrip("-") for l in letters)
        gloss = _frame_gloss(frame) if frame else {"english": "", "swahili": ""}
        segments.append({"original": word, "signs": letters, "transliteration": translit, "pronunciation": translit.replace("ə", "").replace("ʾ", "").replace("ʿ", "") or translit,
                         "meaning": gloss, "source": "ancient ladder lexicon" if frame else "Unicode letter names",
                         "status": "confirmed" if frame else "sign_only", "confidence": "high" if frame else "low"})
    direction = "right_to_left" if script in {"arabic", "old_north_arabian"} else "left_to_right"
    return {"script": script, "language": detected_lang, "segments": segments, "direction": direction}


# ------------------------------------------------------------------ whole-text reading
def _whole_translation(text: str, reading: dict[str, Any]) -> dict[str, Any]:
    sources = {"hieroglyphic": ["old_egyptian", "middle_egyptian"], "cuneiform": ["archaic_sumerian"],
               "ethiopic": ["geez", "old_amharic"], "old_italic": ["old_latin"], "old_north_arabian": ["old_arabic"], "arabic": ["old_arabic"]}
    for source in sources.get(reading["script"], []):
        try:
            result = ladder_translate(text, source, ["english", "swahili"])
        except LadderError:
            continue
        if result["ok"] and not result["parse"]["unknown_words"] and result["meaning"].get("kind") in {"clause", "identity"}:
            return {"english": result["results"]["english"]["text"], "swahili": result["results"]["swahili"]["text"],
                    "status": "grammar_parse", "language": source}
    english = [s["meaning"]["english"] for s in reading["segments"] if s["meaning"]["english"]]
    swahili = [s["meaning"]["swahili"] for s in reading["segments"] if s["meaning"]["swahili"]]
    return {"english": ", ".join(english), "swahili": ", ".join(swahili), "status": "word_by_word" if english else "unread"}


def _script_reader(text: str, script: str, language: str) -> dict[str, Any]:
    if script == "hieroglyphic":
        return read_hieroglyphs(text, language)
    if script == "cuneiform":
        return read_cuneiform(text, language)
    return read_alphabetic(text, script, language)


def _pronounce(translit: str, lang_id: str) -> str:
    if lang_id in {"old_egyptian", "middle_egyptian"}:
        return " ".join(egyptian_pronunciation(part) for part in re.split(r"\s+", translit.replace(".", "")) if part)
    plain = re.sub(r"\d", "", translit).replace("ĝ", "ng").replace("š", "sh").replace("*", "")
    return re.sub(r"ə(?=\b)", "", plain).replace("ʾ", "").replace("ʿ", "")


def read_text(text: str, language: str = "english") -> dict[str, Any] | None:
    from ..ancient.parsing import _exact_key
    script = detect_script(text)
    if not script:
        return None
    tokens = [t for t in re.split(r"[\s፡።·,]+", unicodedata.normalize("NFC", text)) if t and any(char_script(c) for c in t)]
    segments: list[dict[str, Any]] = []
    languages_hit: list[str] = []
    for token in tokens:
        hit = None
        for lang_id in TOKEN_LANGS.get(script, []):
            entry = token_lexicon(lang_id).get(_exact_key(token))
            if entry:
                hit = (lang_id, entry)
                break
        breakdown = _script_reader(token, script, language)
        if hit:
            lang_id, (translit, info) = hit
            languages_hit.append(lang_id)
            signs = [sign for seg in breakdown["segments"] for sign in seg["signs"]]
            segments.append({"original": token, "signs": signs, "transliteration": translit, "pronunciation": _pronounce(translit, lang_id),
                             "meaning": gloss_info(info), "source": "ancient ladder lexicon", "status": "confirmed",
                             "confidence": "high", "grammar": {k: v for k, v in info.items() if k in {"type", "person", "tense", "case", "role"}}})
        else:
            segments.extend(breakdown["segments"])
    reading = {"script": script, "language": TOKEN_LANGS[script][0] if script != "hieroglyphic" else "middle_egyptian",
               "segments": segments, "direction": "right_to_left" if script in {"arabic", "old_north_arabian"} else "left_to_right" if script in {"cuneiform", "old_italic", "ethiopic"} else "as_written"}
    if languages_hit:
        reading["language"] = max(set(languages_hit), key=languages_hit.count)
    reading["translation"] = _whole_translation(text, reading)
    if reading["translation"].get("language"):
        reading["language"] = reading["translation"]["language"]
    return _finish(reading, text, "text", language)


def _finish(reading: dict[str, Any], original: str, source: str, language: str) -> dict[str, Any]:
    lang = _lang(language)
    confirmed = sum(1 for s in reading["segments"] if s["status"] == "confirmed")
    total = max(1, len(reading["segments"]))
    reading.update({
        "ok": bool(reading["segments"]),
        "source": source,
        "original": original,
        "explain_language": lang,
        "script_name": SCRIPTS.get(reading["script"], {}).get("name", {}).get(lang, reading["script"]),
        "language_name": REALIZERS[reading["language"]].name if reading.get("language") in REALIZERS else reading.get("language", ""),
        "coverage": {"confirmed_words": confirmed, "total_words": len(reading["segments"])},
        "confidence": round(min(0.9, 0.35 + 0.55 * confirmed / total), 2) if reading.get("confidence") is None else reading["confidence"],
    })
    reading.setdefault("notes", [])
    if reading["script"] == "hieroglyphic" and source == "text":
        reading["notes"].append(
            "Typed hieroglyphs keep only their order. On a real wall, the signs' faces show the direction: you read toward the faces." if lang == "english"
            else "Hieroglifu zilizoandikwa hapa zinaonyesha mpangilio tu. Ukutani, nyuso za alama zinaonyesha mwelekeo: unasoma kuelekea nyuso hizo.")
    return reading


# ------------------------------------------------------------------ narration (what the guide says)
DIRECTION_WORDS = {
    "english": {"right_to_left": "from right to left", "left_to_right": "from left to right",
                "top_to_bottom": "from top to bottom", "as_written": "in the order it is written"},
    "swahili": {"right_to_left": "kutoka kulia kwenda kushoto", "left_to_right": "kutoka kushoto kwenda kulia",
                "top_to_bottom": "kutoka juu kwenda chini", "as_written": "kwa mpangilio ulioandikwa"},
}


ORDINALS = {
    "english": ["first", "second", "third", "fourth", "fifth", "sixth"],
    "swahili": ["ya kwanza", "ya pili", "ya tatu", "ya nne", "ya tano", "ya sita"],
}


def spoken_sounds(value: str | None) -> str:
    """ꜥnḫ -> 'a, n, kh' : consonants a voice can say."""
    if not value:
        return ""
    parts = []
    for char in unicodedata.normalize("NFC", value):
        if char in _EGY_SOUNDS:
            sound = _EGY_SOUNDS[char][0]
            parts.append({"j": "i", "w": "w"}.get(char, sound))
        elif char.isalpha():
            parts.append(char)
    return ", ".join(parts)


def _say_sign(sign: dict[str, Any], position: int, lang: str) -> str:
    en = lang == "english"
    ordinal = ORDINALS[lang][min(position, 5)]
    role = sign["role"]
    if role == "determinative":
        return (f"the {ordinal} sign is a meaning marker, so you don't say it" if en
                else f"alama {ordinal} ni alama ya maana, kwa hiyo haisomwi")
    if role == "complement":
        return (f"the {ordinal} sign repeats the sound {spoken_sounds(sign.get('value'))} to help you read" if en
                else f"alama {ordinal} inarudia sauti {spoken_sounds(sign.get('value'))} kukusaidia kusoma")
    if role == "affix":
        return (f"the {ordinal} sign is a grammar ending" if en else f"alama {ordinal} ni kiambishi cha kisarufi")
    sounds = spoken_sounds(sign.get("value")) if sign.get("value") else ""
    if sounds:
        return (f"the {ordinal} sign gives the sounds {sounds}" if en else f"alama {ordinal} inatoa sauti {sounds}")
    return (f"the {ordinal} sign isn't in my catalog" if en else f"alama {ordinal} haiko kwenye orodha yangu")


def narrate(reading: dict[str, Any], language: str, detail: str = "full", first_number: int = 1) -> list[dict[str, Any]]:
    """Spoken lesson as [{'text', 'segment'}]; 'segment' tells the card which word to highlight."""
    lang = _lang(language)
    en = lang == "english"
    lines: list[dict[str, Any]] = []

    def say(text: str, segment: int | None = None) -> None:
        lines.append({"text": text, "segment": segment})

    script_name = reading["script_name"]
    direction = DIRECTION_WORDS[lang].get(reading.get("direction") or "as_written", DIRECTION_WORDS[lang]["as_written"])
    if reading.get("summary"):
        say(reading["summary"])
    if reading.get("is_text_present") is False:
        say("I don't see any writing I can read here. Try moving closer, or hold the camera steady on the text." if en
            else "Sioni maandishi ninayoweza kusoma hapa. Sogea karibu, au shikilia kamera bila kutikisika.")
        return lines
    say(f"This is written in {script_name}, and we read it {direction}." if en
        else f"Haya yameandikwa kwa {script_name}, na tunasoma {direction}.")
    if reading.get("direction_reason"):
        say(reading["direction_reason"])
    translation = reading.get("translation", {}).get(lang) or ""
    if translation:
        if reading["translation"].get("status") == "word_by_word":
            say(f"Word by word, it says: {translation}." if en else f"Neno kwa neno, inasema: {translation}.")
        else:
            say(f"Altogether it means: {translation}." if en else f"Kwa ujumla, maana yake ni: {translation}.")
    segments = reading["segments"]
    if detail == "short" or not segments:
        return lines
    say("Let's read it together, one word at a time." if en else "Tusome pamoja, neno moja baada ya jingine.")
    for index, segment in enumerate(segments[:12]):
        number = index + first_number
        meaning = segment["meaning"].get(lang) or segment["meaning"].get("english")
        head = f"Word {number}" if en else f"Neno la {number}"
        if segment["status"] == "sign_only" and not meaning:
            sounds = spoken_sounds(segment["transliteration"]) or segment["pronunciation"]
            say(f"{head} gives the sounds {sounds}, but I can't confirm which word it is." if en
                else f"{head} linatoa sauti {sounds}, lakini sijathibitisha ni neno gani.", index)
            continue
        sound = segment.get("pronunciation") or segment["transliteration"]
        sentence = f"{head} is said {sound}" if en else f"{head} linatamkwa {sound}"
        sentence += (f", and it means {meaning}." if en else f", na maana yake ni {meaning}.") if meaning else "."
        if segment["status"] in {"model_reading", "disputed"}:
            sentence += (" I'm reading this from the photo, so treat it as likely rather than certain." if en
                         else " Nimesoma hili kutoka kwenye picha, kwa hiyo lichukulie kama uwezekano.")
        say(sentence, index)
        signs = segment["signs"]
        if reading["script"] == "hieroglyphic" and signs:
            if len(signs) == 1 and signs[0]["role"] in {"logogram", "triliteral", "biliteral"}:
                say("Here a single sign writes the whole word." if en else "Hapa alama moja inaandika neno zima.", index)
            elif len(signs) > 1:
                parts = [_say_sign(sign, position, lang) for position, sign in enumerate(signs[:5])]
                say(("In this word, " if en else "Katika neno hili, ") + "; ".join(parts) + ".", index)
    if len(segments) > 12:
        say(f"There are {len(segments) - 12} more words on the card." if en else f"Kuna maneno {len(segments) - 12} zaidi kwenye kadi.")
    if reading["script"] == "hieroglyphic":
        say("Egyptologists add the e sounds so the words can be spoken; the real ancient vowels are unknown." if en
            else "Wataalamu huongeza sauti ya e ili maneno yatamkike; irabu halisi za kale hazijulikani.")
    say("Say quiz me when you want to try reading it yourself." if en else "Sema nijaribu ukitaka kujaribu kusoma mwenyewe.")
    return lines


# ------------------------------------------------------------------ vision (photo / camera)
TEACHER_INSTRUCTIONS = """
You are a patient teacher reading an image aloud to a learner, the way one reads a book with a child.
Read ONLY what the image actually shows. If writing is too small, damaged or decorative, say so instead of guessing.
Handle any script: Egyptian hieroglyphs, cuneiform, Ge'ez/Ethiopic, Old Latin or Latin inscriptions, Arabic or Safaitic,
and ordinary modern text or signs. For Egyptian, the signs' faces point toward the start of the line; use that for direction.
Return ONLY a JSON object with keys:
is_text_present (bool), script (one of hieroglyphic, cuneiform, ethiopic, latin, arabic, old_north_arabian, greek, modern, other),
language (string, e.g. "Middle Egyptian", "Sumerian", "Ge'ez", "Latin", "Arabic", "English"),
reading_direction (right_to_left | left_to_right | top_to_bottom), direction_reason (one sentence in the learner's language),
summary (one sentence in the learner's language describing what the image shows),
segments (array, reading order, max 20) of objects with: original (the characters as Unicode if possible, else ""),
transliteration (standard scholarly transliteration, "" for modern text), pronunciation (how a learner says it),
meaning_english, meaning_learner (in the learner's language),
signs (array, optional) of objects: glyph, gardiner (Gardiner code or null), value, role (uniliteral|biliteral|triliteral|logogram|determinative|complement|syllable|letter|unknown),
confidence (0..1),
translation_english, translation_learner (whole text in the learner's language), uncertainties (array of strings), overall_confidence (0..1).
Mark uncertain readings with low confidence. Never invent Gardiner codes; use null.
""".strip()


async def read_image(image_data_url: str, language: str, question: str = "", detail: str = "high") -> dict[str, Any]:
    """Ask the configured multimodal model for a teacher-style reading, then cross-check it."""
    from ..ai import _responses_request
    from .personas import LANGUAGES
    lang = _lang(language)
    prompt = (f"The learner's language is {LANGUAGES.get(language, LANGUAGES['english'])['label']} ({language}). "
              f"The learner asks: {question or 'What does this say? Please read it to me.'}")
    raw = await _responses_request(
        [{"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": image_data_url, "detail": detail}],
        TEACHER_INSTRUCTIONS,
    )
    return reading_from_model(raw, language)


def reading_from_model(raw: dict[str, Any], language: str) -> dict[str, Any]:
    """Normalize a model's reading and check each word against the deterministic sign and word data."""
    lang = _lang(language)
    script = str(raw.get("script") or "other").lower()
    script_key = {"latin": "old_italic", "ethiopic": "ethiopic", "hieroglyphic": "hieroglyphic", "cuneiform": "cuneiform",
                  "arabic": "arabic", "old_north_arabian": "old_north_arabian"}.get(script, script)
    segments = []
    for item in (raw.get("segments") or [])[:20]:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "")
        transliteration = str(item.get("transliteration") or "")
        meaning_en = str(item.get("meaning_english") or "")
        meaning_user = str(item.get("meaning_learner") or meaning_en)
        signs = []
        for sign in (item.get("signs") or [])[:12]:
            if isinstance(sign, dict):
                role = str(sign.get("role") or "unknown")
                role = role if role in ROLE_LABELS[lang] else "unknown"
                signs.append({"glyph": str(sign.get("glyph") or ""), "code": sign.get("gardiner"), "value": sign.get("value"),
                              "values": [sign.get("value")] if sign.get("value") else [], "role": role, "role_label": ROLE_LABELS[lang][role]})
        status, source = "model_reading", "vision model"
        # Cross-check: if the model gave Unicode signs we can read, compare with our own reading.
        own = read_text(original, language) if original and detect_script(original) else None
        if own and own["segments"]:
            own_words = {s["transliteration"] for s in own["segments"] if s["status"] == "confirmed"}
            if transliteration and transliteration in own_words:
                status, source = "confirmed", own["segments"][0]["source"]
            elif own_words:
                status = "disputed"
            if not signs:
                signs = [s for seg in own["segments"] for s in seg["signs"]]
        elif transliteration and script_key == "hieroglyphic" and _gloss_translit(transliteration):
            status, source = "confirmed", "Middle Egyptian lexicon"
        pronunciation = str(item.get("pronunciation") or (egyptian_pronunciation(transliteration) if script_key == "hieroglyphic" and transliteration else transliteration))
        confidence = item.get("confidence")
        segments.append({"original": original, "signs": signs, "transliteration": transliteration, "pronunciation": pronunciation,
                         "meaning": {"english": meaning_en or meaning_user, "swahili": meaning_user if language == "swahili" else "",
                                     **({language: meaning_user} if language not in {"english", "swahili"} and meaning_user else {})},
                         "source": source, "status": status,
                         "confidence": "high" if isinstance(confidence, (int, float)) and confidence >= 0.75 else "medium" if isinstance(confidence, (int, float)) and confidence >= 0.45 else "low"})
    reading = {
        "script": script_key,
        "language": str(raw.get("language") or ""),
        "direction": raw.get("reading_direction") if raw.get("reading_direction") in DIRECTION_WORDS["english"] else "as_written",
        "direction_reason": str(raw.get("direction_reason") or ""),
        "summary": str(raw.get("summary") or ""),
        "segments": segments,
        "translation": {"english": str(raw.get("translation_english") or raw.get("translation_learner") or ""),
                        language: str(raw.get("translation_learner") or raw.get("translation_english") or ""),
                        "status": "model_reading"},
        "notes": [str(u) for u in (raw.get("uncertainties") or [])[:6]],
        "confidence": float(raw.get("overall_confidence") or 0.0),
        "is_text_present": bool(raw.get("is_text_present", bool(segments))),
    }
    if script_key in SCRIPTS:
        reading["script_name"] = SCRIPTS[script_key]["name"][lang]
    finished = _finish(reading, "", "image", language)
    if script_key not in SCRIPTS:
        finished["script_name"] = reading["language"] or script
        finished["language_name"] = reading["language"]
    return finished


def reading_from_detector(analysis: dict[str, Any], language: str) -> dict[str, Any] | None:
    """Turn the local ONNX sign detector's output into a reading of the detected signs."""
    glyphs = "".join(s.get("unicode") or "" for s in analysis.get("sign_candidates", []) if s.get("unicode"))
    if not glyphs:
        return None
    reading = read_text(glyphs, language)
    if reading:
        reading["source"] = "image"
        reading["direction"] = "as_written"
        reading["notes"].append("Signs were found by the on-device detector, ordered by position; check the reading direction against the signs' faces."
                                if _lang(language) == "english" else
                                "Alama zimegunduliwa na kitambuzi cha ndani na kupangwa kwa nafasi; hakiki mwelekeo kwa kuangalia nyuso za alama.")
        reading["confidence"] = round(min(reading["confidence"], float(analysis.get("overall_confidence") or 0.5)), 2)
    return reading


def reading_summary(reading: dict[str, Any]) -> str:
    """Compact fact sheet for the language model's environment layer."""
    slim = {
        "script": reading.get("script"), "language": reading.get("language_name"), "direction": reading.get("direction"),
        "translation": reading.get("translation"),
        "words": [{"original": s["original"], "transliteration": s["transliteration"], "say": s["pronunciation"],
                   "meaning": s["meaning"], "status": s["status"]} for s in reading.get("segments", [])[:20]],
    }
    return "Current reading lesson (verified data, use these forms): " + json.dumps(slim, ensure_ascii=False)[:4000]


def warm_up() -> dict[str, float]:
    """Build every reading and parsing index ahead of the first learner (called at startup in a thread)."""
    import time

    from ..ancient.parsing import form_index
    timings: dict[str, float] = {}
    start = time.perf_counter()
    hieroglyph_words()
    cuneiform_words()
    for langs in TOKEN_LANGS.values():
        for lang in langs:
            token_lexicon(lang)
    for lang in REALIZERS:
        if lang not in {"english", "swahili"}:
            form_index(lang)
    timings["total_seconds"] = round(time.perf_counter() - start, 2)
    return timings
