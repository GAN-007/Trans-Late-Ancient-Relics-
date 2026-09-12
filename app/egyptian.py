from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from typing import Optional

DATA = Path(__file__).parent / "data"

UNILITERALS = {
    "ꜣ":{"glyph":"𓄿","gardiner":"G1","mdc":"A","name":"Egyptian vulture"},
    "j":{"glyph":"𓇋","gardiner":"M17","mdc":"i","name":"reed leaf"},
    "y":{"glyph":"𓇌","gardiner":"M17A","mdc":"y","name":"two reed leaves"},
    "ꜥ":{"glyph":"𓂝","gardiner":"D36","mdc":"a","name":"forearm"},
    "w":{"glyph":"𓅱","gardiner":"G43","mdc":"w","name":"quail chick"},
    "b":{"glyph":"𓃀","gardiner":"D58","mdc":"b","name":"foot"},
    "p":{"glyph":"𓊪","gardiner":"Q3","mdc":"p","name":"stool"},
    "f":{"glyph":"𓆑","gardiner":"I9","mdc":"f","name":"horned viper"},
    "m":{"glyph":"𓅓","gardiner":"G17","mdc":"m","name":"owl"},
    "n":{"glyph":"𓈖","gardiner":"N35","mdc":"n","name":"water ripple"},
    "r":{"glyph":"𓂋","gardiner":"D21","mdc":"r","name":"mouth"},
    "h":{"glyph":"𓉔","gardiner":"O4","mdc":"h","name":"reed shelter"},
    "ḥ":{"glyph":"𓎛","gardiner":"V28","mdc":"H","name":"twisted wick"},
    "ḫ":{"glyph":"𓐍","gardiner":"Aa1","mdc":"x","name":"Aa1 sign"},
    "ẖ":{"glyph":"𓄡","gardiner":"F32","mdc":"X","name":"animal belly"},
    "z":{"glyph":"𓊃","gardiner":"O34","mdc":"z","name":"door bolt"},
    "s":{"glyph":"𓋴","gardiner":"S29","mdc":"s","name":"folded cloth"},
    "š":{"glyph":"𓈙","gardiner":"N37","mdc":"S","name":"pool"},
    "q":{"glyph":"𓈎","gardiner":"N29","mdc":"q","name":"hill slope"},
    "k":{"glyph":"𓎡","gardiner":"V31","mdc":"k","name":"basket with handle"},
    "g":{"glyph":"𓎼","gardiner":"W11","mdc":"g","name":"jar stand"},
    "t":{"glyph":"𓏏","gardiner":"X1","mdc":"t","name":"bread loaf"},
    "ṯ":{"glyph":"𓍿","gardiner":"V13","mdc":"T","name":"tethering rope"},
    "d":{"glyph":"𓂧","gardiner":"D46","mdc":"d","name":"hand"},
    "ḏ":{"glyph":"𓆓","gardiner":"I10","mdc":"D","name":"cobra"},
}
GLYPH_TO_UNILITERAL = {v["glyph"]:k for k,v in UNILITERALS.items()}
MDC_TO_TRANSLIT = {"A":"ꜣ","a":"ꜥ","H":"ḥ","x":"ḫ","X":"ẖ","S":"š","T":"ṯ","D":"ḏ"}
TRANSLIT_TO_MDC = {v:k for k,v in MDC_TO_TRANSLIT.items()}

def load_lexicon():
    entries = []
    for path in sorted((DATA / "lexicon").glob("*.json")):
        entries.extend(json.loads(path.read_text(encoding="utf-8")))
    return entries

LEXICON = load_lexicon()

def normalize_transliteration(text: str) -> str:
    text = unicodedata.normalize("NFC", text.strip())
    # Normalize common i/j spellings only conservatively.
    return text

def mdc_to_transliteration(mdc: str) -> str:
    out = []
    for ch in mdc:
        out.append(MDC_TO_TRANSLIT.get(ch, ch))
    return "".join(out)

def transliteration_to_mdc(text: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFC", text):
        out.append(TRANSLIT_TO_MDC.get(ch, ch))
    return "".join(out)

def lookup_by_translit(text: str, pos: Optional[str]=None) -> list[dict]:
    q = normalize_transliteration(text).lower()
    matches = []
    for e in LEXICON:
        if e["transliteration"].lower() == q and (pos is None or e["pos"] == pos):
            matches.append(e)
    return matches

def search_dictionary(query: str="", language: str="all", pos: Optional[str]=None, limit: int=50) -> list[dict]:
    q = unicodedata.normalize("NFC", query.strip()).lower()
    scored = []
    for entry in LEXICON:
        if pos and pos.lower() not in entry.get("pos","").lower():
            continue
        fields = []
        if language in ("all","egyptian","transliteration"):
            fields.append(entry["transliteration"])
        if language in ("all","english"):
            fields += entry.get("english", [])
        if language in ("all","swahili"):
            fields += entry.get("swahili", [])
        hay = " | ".join(fields).lower()
        if not q:
            score = 1
        elif entry["transliteration"].lower() == q:
            score = 100
        elif any(str(x).lower() == q for x in entry.get("english",[]) + entry.get("swahili",[])):
            score = 90
        elif hay.startswith(q):
            score = 70
        elif q in hay:
            score = 50
        else:
            continue
        scored.append((score, entry))
    scored.sort(key=lambda x:(-x[0], x[1]["transliteration"]))
    return [x[1] for x in scored[:limit]]

def uniliteral_spell(transliteration: str) -> dict:
    """Render a transliteration with uniliteral signs only.
    This is a phonetic fallback, not a claim about authentic historical spelling.
    """
    glyphs, gardiner, unknown = [], [], []
    text = normalize_transliteration(transliteration)
    # ignore punctuation used by Egyptologists for morpheme boundaries
    for ch in text:
        if ch in ".=-()[]{} ":
            if ch == " ":
                glyphs.append(" ")
                gardiner.append("/")
            continue
        info = UNILITERALS.get(ch)
        if info:
            glyphs.append(info["glyph"])
            gardiner.append(info["gardiner"])
        else:
            unknown.append(ch)
            glyphs.append(f"[{ch}]")
    return {
        "transliteration": text,
        "hieroglyphs": "".join(glyphs),
        "gardiner": " ".join(gardiner),
        "authenticity":"phonetic_fallback",
        "unknown":unknown,
        "warning":"Uniliteral fallback represents consonantal values but may not match historically attested orthography."
    }

def hieroglyphize_word(transliteration: str) -> dict:
    matches = lookup_by_translit(transliteration)
    canonical = [e for e in matches if e.get("hieroglyphs")]
    if canonical:
        # If multiple entries share the same transliteration but one has canonical glyphs,
        # surface all lexical senses while keeping the canonical sign form.
        e = canonical[0]
        return {
            "transliteration": transliteration,
            "hieroglyphs": e["hieroglyphs"],
            "gardiner": " ".join(e.get("gardiner",[])),
            "mdc": e.get("mdc"),
            "authenticity":"lexicon_canonical",
            "senses":[{"english":x.get("english",[]),"swahili":x.get("swahili",[]),"pos":x.get("pos")} for x in matches],
            "warning":"Canonical/logographic form in this teaching lexicon; real inscriptions may use alternative spellings, phonetic complements, or determinatives."
        }
    result = uniliteral_spell(transliteration)
    result["senses"] = [{"english":x.get("english",[]),"swahili":x.get("swahili",[]),"pos":x.get("pos")} for x in matches]
    return result

def hieroglyphize_phrase(transliteration: str) -> dict:
    words = [w for w in re.split(r"\s+", transliteration.strip()) if w]
    rendered = [hieroglyphize_word(w) for w in words]
    return {
        "transliteration": transliteration,
        "hieroglyphs":"  ".join(r["hieroglyphs"] for r in rendered),
        "words":rendered,
        "warning":"Word order is preserved. Unicode output is horizontal; monumental block arrangement is a separate layout problem."
    }

def parse_uniliterals(glyphs: str) -> dict:
    translit = []
    unknown = []
    for ch in glyphs:
        if ch.isspace():
            translit.append(" ")
        elif ch in GLYPH_TO_UNILITERAL:
            translit.append(GLYPH_TO_UNILITERAL[ch])
        else:
            unknown.append(ch)
            translit.append(f"[{ch}]")
    return {
        "hieroglyphs":glyphs,
        "transliteration":"".join(translit),
        "unknown_signs":unknown,
        "warning":"This parser only treats the standard uniliteral signs as alphabetic values. Other hieroglyphs can be biliterals, triliterals, logograms, determinatives, or ambiguous signs and require sign-level analysis."
    }

def uniliteral_table() -> list[dict]:
    return [{"value":k, **v} for k,v in UNILITERALS.items()]
