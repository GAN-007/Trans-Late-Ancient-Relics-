from __future__ import annotations

import re
import unicodedata
from typing import Any

from .egyptian import current_lexicon, hieroglyphize_phrase, search_dictionary


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text.strip().lower()))


def _index(language: str) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for entry in current_lexicon():
        for gloss in entry.get(language, []):
            idx.setdefault(_normalize(str(gloss)), []).append(entry)
    return idx


def _best_lexeme(term: str, language: str) -> dict | None:
    q = _normalize(term)
    idx = _index(language)
    if q in idx:
        # Prefer reviewed/high-confidence entries, but keep ambiguity for the caller.
        entries = sorted(
            idx[q],
            key=lambda e: (
                0 if e.get("runtime_overlay") else 1,
                {"high": 0, "medium": 1, "low": 2}.get(e.get("confidence"), 3),
            ),
        )
        return entries[0]
    candidates = search_dictionary(term, language=language, limit=10)
    return candidates[0] if candidates else None


def lexical_candidates(term: str, language: str, limit: int = 10) -> list[dict]:
    q = _normalize(term)
    idx = _index(language)
    exact = idx.get(q, [])
    if exact:
        return exact[:limit]
    return search_dictionary(term, language=language, limit=limit)


PHRASE_TEMPLATES = [
    {
        "name":"identity_i_am",
        "english":re.compile(r"^i am (?:a |an )?(.+)$", re.I),
        "swahili":re.compile(r"^(?:mimi )?ni (.+)$", re.I),
        "builder":lambda x: f"jnk {x}",
        "explanation":"Independent pronoun jnk followed by a nominal predicate.",
    },
    {
        "name":"my_name",
        "english":re.compile(r"^my name is (.+)$", re.I),
        "swahili":re.compile(r"^jina langu ni (.+)$", re.I),
        "builder":lambda _x: "rn.j pw",
        "explanation":"Pedagogical nominal pattern rn.j pw. The modern proper name is kept separate because foreign-name spelling is its own transcription problem.",
    },
    {
        "name":"house_is_good",
        "english":re.compile(r"^the house is (good|beautiful)$", re.I),
        "swahili":re.compile(r"^nyumba ni (nzuri|rembo)$", re.I),
        "builder":lambda _x: "nfr pr",
        "explanation":"Illustrative adjectival-predicate pattern; exact discourse syntax remains context-sensitive.",
    },
    {
        "name":"in_the_house",
        "english":re.compile(r"^in the house$", re.I),
        "swahili":re.compile(r"^(?:ndani ya|katika) nyumba$", re.I),
        "builder":lambda _x: "m pr",
        "explanation":"Preposition m + noun pr.",
    },
    {
        "name":"to_the_town",
        "english":re.compile(r"^(?:to|toward) the (?:town|city)$", re.I),
        "swahili":re.compile(r"^kuelekea (?:mjini|mji|jijini|jiji)$", re.I),
        "builder":lambda _x: "r njwt",
        "explanation":"Preposition r + noun njwt.",
    },
]


def translate_word(text: str, source: str, target: str="egyptian") -> dict:
    entries = lexical_candidates(text, source, limit=20)
    if not entries:
        return {
            "ok":False,
            "source":text,
            "source_language":source,
            "target_language":target,
            "message":"No secure lexicon entry found. The system refuses to invent an Ancient Egyptian word.",
            "confidence":0.0,
        }
    entry = entries[0]
    ambiguities = [
        {
            "transliteration": e["transliteration"],
            "pos": e.get("pos"),
            "english": e.get("english", []),
            "swahili": e.get("swahili", []),
            "confidence": e.get("confidence"),
        }
        for e in entries[1:]
        if e["transliteration"] != entry["transliteration"] or e.get("pos") != entry.get("pos")
    ]
    if target == "egyptian":
        rendered = hieroglyphize_phrase(entry["transliteration"])
        return {
            "ok":True,
            "source":text,
            "source_language":source,
            "target_language":"middle_egyptian",
            "transliteration":entry["transliteration"],
            "hieroglyphs":rendered["hieroglyphs"],
            "english":entry.get("english",[]),
            "swahili":entry.get("swahili",[]),
            "pos":entry.get("pos"),
            "notes":entry.get("notes"),
            "confidence":0.95 if entry.get("confidence")=="high" else 0.75 if entry.get("confidence")=="medium" else 0.55,
            "mode":"dictionary",
            "alternatives": ambiguities,
            "orthography": rendered,
        }
    values = entry.get(target, [])
    return {
        "ok":True,
        "source":text,
        "target_language":target,
        "translations":values,
        "entry":entry,
        "alternatives": ambiguities,
        "confidence":0.9,
    }


def translate_phrase(text: str, source: str) -> dict:
    normalized = _normalize(text)
    for template in PHRASE_TEMPLATES:
        rx = template.get(source)
        if not rx:
            continue
        match = rx.match(normalized)
        if not match:
            continue
        captured = match.group(1) if match.groups() else ""
        proper_name = None
        if template["name"] == "identity_i_am":
            lexical = _best_lexeme(captured, source)
            if not lexical:
                return {
                    "ok":False,
                    "source":text,
                    "message":f"The predicate '{captured}' is not in the reviewed lexicon, so the historical translation is not guessed.",
                    "confidence":0.0,
                    "unresolved":[captured],
                }
            translit = template["builder"](lexical["transliteration"])
        elif template["name"] == "my_name":
            translit = template["builder"](captured)
            proper_name = captured.strip()
        else:
            translit = template["builder"](captured)
        rendered = hieroglyphize_phrase(translit)
        result = {
            "ok":True,
            "source":text,
            "source_language":source,
            "transliteration":translit,
            "hieroglyphs":rendered["hieroglyphs"],
            "analysis":template["explanation"],
            "mode":"grammar_template",
            "confidence":0.75,
            "warning":"Pedagogical translation, not a claim that every historical discourse context would use exactly this construction.",
            "orthography": rendered,
        }
        if proper_name:
            result["proper_name"] = proper_name
            result["proper_name_warning"] = "The modern name is not automatically turned into a supposedly authentic ancient spelling. Use the ESHB/name-transcription workflow separately."
        return result

    tokens = re.findall(r"[\wꜣꜥḥḫẖšṯḏ'-]+", normalized, flags=re.UNICODE)
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for tok in tokens:
        candidates = lexical_candidates(tok, source, limit=6)
        if candidates:
            resolved.append(
                {
                    "source":tok,
                    "candidates":[
                        {
                            "transliteration": e["transliteration"],
                            "english":e.get("english",[]),
                            "swahili":e.get("swahili",[]),
                            "pos":e.get("pos"),
                            "confidence":e.get("confidence"),
                        }
                        for e in candidates
                    ],
                }
            )
        else:
            unresolved.append(tok)
    return {
        "ok":False,
        "source":text,
        "source_language":source,
        "mode":"analysis_only",
        "resolved":resolved,
        "unresolved":unresolved,
        "message":"The sentence does not match a verified grammar template. Lexical candidates are shown, but the system will not pretend that word substitution is an authentic Egyptian translation.",
        "confidence":0.0,
    }


def egyptian_to_modern(transliteration: str, target: str="english") -> dict:
    words = [w for w in re.split(r"\s+", transliteration.strip()) if w]
    output = []
    ambiguity = []
    lexicon = current_lexicon()
    for word in words:
        base = word.split(".")[0]
        matches = [e for e in lexicon if e["transliteration"].lower() == base.lower()]
        if not matches:
            output.append(f"[{word}]")
            continue
        senses = []
        for entry in matches:
            senses += entry.get(target, [])
        senses = list(dict.fromkeys(senses))
        output.append(senses[0] if senses else f"[{word}]")
        if len(senses)>1:
            ambiguity.append({"word":word,"senses":senses})
    return {
        "source":transliteration,
        "target_language":target,
        "literal_gloss":" ".join(output),
        "ambiguity":ambiguity,
        "warning":"This is a lexical gloss. A proper historical translation requires morphological and syntactic parsing before choosing final English/Swahili wording.",
    }
