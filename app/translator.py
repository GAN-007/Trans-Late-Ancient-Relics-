from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Iterable

from .egyptian import all_lexicon_entries, hieroglyphize_phrase, search_dictionary
from . import storage
from .linguistics import analyze_morphology, detect_intent


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text.strip().lower()))


def _index(language: str) -> dict[str, list[dict]]:
    idx: dict[str, list[dict]] = {}
    for e in all_lexicon_entries():
        for gloss in e.get(language, []):
            idx.setdefault(_normalize(str(gloss)), []).append(e)
    return idx


def _entries_for(term: str, language: str) -> list[dict]:
    q = _normalize(term)
    idx = _index(language)
    if q in idx:
        return idx[q]
    return search_dictionary(term, language=language, limit=12)


PHRASE_TEMPLATES = [
    {
        "name": "identity_i_am",
        "english": re.compile(r"^i am (?:a |an )?(.+)$", re.I),
        "swahili": re.compile(r"^(?:mimi )?ni (.+)$", re.I),
        "builder": lambda x: f"jnk {x}",
        "explanation": "Independent pronoun jnk followed by a nominal predicate.",
        "intent": "identity",
    },
    {
        "name": "my_name",
        "english": re.compile(r"^my name is (.+)$", re.I),
        "swahili": re.compile(r"^jina langu ni (.+)$", re.I),
        "builder": lambda x: f"rn.j pw {x}",
        "explanation": "Pedagogical nominal pattern using rn.j 'my name' and pw; the personal name remains a separate transcription problem.",
        "intent": "self_introduction",
    },
    {
        "name": "house_is_good",
        "english": re.compile(r"^the house is (good|beautiful)$", re.I),
        "swahili": re.compile(r"^nyumba ni (nzuri|rembo)$", re.I),
        "builder": lambda x: "nfr pr",
        "explanation": "Illustrative adjectival-predicate pattern. Exact syntax depends on period and discourse.",
        "intent": "description",
    },
    {
        "name": "in_the_house",
        "english": re.compile(r"^in the house$", re.I),
        "swahili": re.compile(r"^(?:ndani ya|katika) nyumba$", re.I),
        "builder": lambda x: "m pr",
        "explanation": "Preposition m + noun pr.",
        "intent": "location",
    },
    {
        "name": "to_the_town",
        "english": re.compile(r"^(?:to|toward) the (?:town|city)$", re.I),
        "swahili": re.compile(r"^kuelekea (?:mjini|mji|jijini|jiji)$", re.I),
        "builder": lambda x: "r njwt",
        "explanation": "Preposition r + noun njwt.",
        "intent": "destination",
    },
]


@dataclass
class Candidate:
    rank: int
    transliteration: str | None
    hieroglyphs: str | None
    literal_translation: str | None
    natural_translation: str | None
    confidence: float
    confidence_label: str
    rationale: str
    assumptions: list[str]
    ambiguities: list[dict]
    provenance: list[dict]


def confidence_label(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    if score >= 0.45:
        return "low"
    return "insufficient"


def _lexeme_provenance(entry: dict) -> dict:
    p = entry.get("provenance") or {}
    return {
        "type": p.get("type", "curated_teaching_lexicon"),
        "transliteration": entry.get("transliteration"),
        "pos": entry.get("pos"),
        "confidence": entry.get("confidence"),
        **({"proposal_id": p["proposal_id"]} if p.get("proposal_id") else {}),
    }


def translate_word(text: str, source: str, target: str = "egyptian") -> dict:
    entries = _entries_for(text, source)
    exact = [e for e in entries if any(_normalize(g) == _normalize(text) for g in e.get(source, []))]
    entries = exact or entries
    exact_match = bool(exact)
    if not entries:
        storage.record_unresolved(text, source)
        return {
            "ok": False,
            "source": text,
            "source_language": source,
            "target_language": target,
            "message": "No secure lexicon entry found. The system refuses to invent an Ancient Egyptian word.",
            "confidence": 0.0,
            "candidates": [],
            "exact_match": False,
        }
    if target == "egyptian":
        candidates = []
        for rank, entry in enumerate(entries[:5], 1):
            rendered = hieroglyphize_phrase(entry["transliteration"])
            score = 0.95 if entry.get("confidence") in {"high", "reviewed"} else 0.75
            candidates.append(asdict(Candidate(
                rank=rank,
                transliteration=entry["transliteration"],
                hieroglyphs=rendered["hieroglyphs"],
                literal_translation=(entry.get("english") or [None])[0] if source != "english" else text,
                natural_translation=None,
                confidence=score,
                confidence_label=confidence_label(score),
                rationale=f"Dictionary sense: {entry.get('pos', 'unknown part of speech')}",
                assumptions=[],
                ambiguities=[{"alternative_senses": entry.get("english", []), "swahili": entry.get("swahili", [])}] if len(entry.get("english", [])) + len(entry.get("swahili", [])) > 2 else [],
                provenance=[_lexeme_provenance(entry)],
            )))
        best = candidates[0]
        return {
            "ok": True,
            "source": text,
            "source_language": source,
            "target_language": "middle_egyptian",
            "transliteration": best["transliteration"],
            "hieroglyphs": best["hieroglyphs"],
            "confidence": best["confidence"],
            "mode": "dictionary",
            "candidates": candidates,
            "exact_match": exact_match,
        }
    translations = []
    for entry in entries:
        translations.extend(entry.get(target, []))
    translations = list(dict.fromkeys(translations))
    return {
        "ok": True,
        "source": text,
        "target_language": target,
        "translations": translations,
        "confidence": 0.9,
        "candidates": [{"rank": i + 1, "text": t} for i, t in enumerate(translations[:8])],
        "exact_match": exact_match,
    }


def _template_translation(text: str, source: str) -> dict | None:
    normalized = _normalize(text)
    for template in PHRASE_TEMPLATES:
        rx = template.get(source)
        if not rx:
            continue
        m = rx.match(normalized)
        if not m:
            continue
        captured = m.group(1) if m.groups() else ""
        assumptions: list[str] = []
        if template["name"] == "identity_i_am":
            lexical = _entries_for(captured, source)
            exact = [e for e in lexical if any(_normalize(g) == _normalize(captured) for g in e.get(source, []))]
            lexical = exact or lexical
            if not lexical:
                storage.record_unresolved(captured, source, text)
                return {
                    "ok": False,
                    "source": text,
                    "message": f"The predicate '{captured}' is not in the reviewed lexicon, so the historical translation is not guessed.",
                    "confidence": 0.0,
                    "unresolved": [captured],
                    "candidates": [],
                }
            candidate_entries = lexical[:3]
            outputs = []
            for rank, entry in enumerate(candidate_entries, 1):
                translit = template["builder"](entry["transliteration"])
                rendered = hieroglyphize_phrase(translit)
                score = 0.83 if rank == 1 else 0.72
                outputs.append(asdict(Candidate(
                    rank=rank,
                    transliteration=translit,
                    hieroglyphs=rendered["hieroglyphs"],
                    literal_translation=text,
                    natural_translation=text,
                    confidence=score,
                    confidence_label=confidence_label(score),
                    rationale=template["explanation"],
                    assumptions=["Pedagogical Middle Egyptian sentence pattern; discourse may prefer another construction."],
                    ambiguities=[{"predicate_source": captured, "selected_lexeme": entry["transliteration"], "other_senses": entry.get(source, [])}],
                    provenance=[{"type": "grammar_template", "template": template["name"]}, _lexeme_provenance(entry)],
                )))
            return {
                "ok": True,
                "source": text,
                "source_language": source,
                "target_language": "middle_egyptian",
                "mode": "grammar_template",
                "intent": template["intent"],
                "transliteration": outputs[0]["transliteration"],
                "hieroglyphs": outputs[0]["hieroglyphs"],
                "confidence": outputs[0]["confidence"],
                "candidates": outputs,
                "warning": "Pedagogical translation. Context, date, genre and intended emphasis can change the preferred Egyptian construction.",
            }
        translit = template["builder"](captured)
        if template["name"] == "my_name":
            assumptions.append("The personal name is preserved as modern text and should be separately transcribed for a historical-style name spelling.")
        rendered = hieroglyphize_phrase(translit)
        output = asdict(Candidate(
            rank=1,
            transliteration=translit,
            hieroglyphs=rendered["hieroglyphs"],
            literal_translation=text,
            natural_translation=text,
            confidence=0.76,
            confidence_label="medium",
            rationale=template["explanation"],
            assumptions=assumptions + ["Pedagogical Middle Egyptian pattern."],
            ambiguities=[],
            provenance=[{"type": "grammar_template", "template": template["name"]}],
        ))
        return {
            "ok": True,
            "source": text,
            "source_language": source,
            "target_language": "middle_egyptian",
            "mode": "grammar_template",
            "intent": template["intent"],
            "transliteration": translit,
            "hieroglyphs": rendered["hieroglyphs"],
            "confidence": output["confidence"],
            "candidates": [output],
            "warning": "Pedagogical translation. Context can change the best historical construction.",
        }
    return None


def translate_phrase(text: str, source: str, context: str = "", intent: str = "") -> dict:
    templated = _template_translation(text, source)
    if templated:
        if context:
            templated["context"] = context
        if intent:
            templated["requested_intent"] = intent
        return templated

    normalized = _normalize(text)
    tokens = re.findall(r"[\wꜣꜥḥḫẖšṯḏ'-]+", normalized, flags=re.UNICODE)
    resolved, unresolved = [], []
    for tok in tokens:
        entries = _entries_for(tok, source)
        exact = [e for e in entries if any(_normalize(g) == tok for g in e.get(source, []))]
        entries = exact or entries
        if entries:
            resolved.append({
                "source": tok,
                "candidates": [
                    {
                        "transliteration": e.get("transliteration"),
                        "pos": e.get("pos"),
                        "english": e.get("english", []),
                        "swahili": e.get("swahili", []),
                        "provenance": _lexeme_provenance(e),
                    }
                    for e in entries[:5]
                ],
            })
        else:
            unresolved.append(tok)
            storage.record_unresolved(tok, source, context or text)

    lexical_coverage = (len(resolved) / len(tokens)) if tokens else 0.0
    return {
        "ok": False,
        "source": text,
        "source_language": source,
        "target_language": "middle_egyptian",
        "mode": "analysis_only",
        "context": context,
        "requested_intent": intent,
        "resolved": resolved,
        "unresolved": unresolved,
        "lexical_coverage": round(lexical_coverage, 3),
        "confidence": 0.0,
        "candidates": [],
        "message": "The sentence does not match a reviewed grammar pattern. Lexical possibilities are shown, but the system will not present word substitution as an authentic Egyptian sentence.",
    }


def egyptian_to_modern(transliteration: str, target: str = "english", context: str = "") -> dict:
    words = [w for w in re.split(r"\s+", transliteration.strip()) if w]
    gloss_tokens, ambiguity, provenance = [], [], []
    candidates_per_word = []
    for word in words:
        base = word.split(".")[0]
        matches = [e for e in all_lexicon_entries() if e.get("transliteration", "").lower() == base.lower()]
        if not matches:
            gloss_tokens.append(f"[{word}]")
            candidates_per_word.append({"word": word, "senses": []})
            storage.record_unresolved(base, "egyptian", context or transliteration)
            continue
        senses: list[str] = []
        word_prov = []
        for e in matches:
            senses += e.get(target, [])
            word_prov.append(_lexeme_provenance(e))
        senses = list(dict.fromkeys(senses))
        gloss_tokens.append(senses[0] if senses else f"[{word}]")
        candidates_per_word.append({"word": word, "senses": senses})
        provenance.extend(word_prov)
        if len(senses) > 1:
            ambiguity.append({"word": word, "senses": senses})
    literal = " ".join(gloss_tokens)
    score = 0.82 if words and all(x["senses"] for x in candidates_per_word) else 0.45
    return {
        "ok": bool(words),
        "source": transliteration,
        "source_language": "egyptian",
        "target_language": target,
        "literal_gloss": literal,
        "natural_translation": literal,
        "word_analysis": candidates_per_word,
        "morphology": analyze_morphology(transliteration),
        "ambiguity": ambiguity,
        "confidence": score,
        "confidence_label": confidence_label(score),
        "provenance": provenance,
        "context": context,
        "warning": "This is a lexical/morphological starting point. A publishable historical translation requires syntactic parsing, genre/period context and sign-level evidence.",
    }


def contextual_translate(text: str, source: str, target: str, context: str = "", intent: str = "", mode: str = "careful") -> dict:
    detected_intent = detect_intent(text, source) if source in {"english", "swahili"} else {"primary": "historical_text", "signals": [], "confidence": 0.5}
    effective_intent = intent.strip() or detected_intent["primary"]
    if source == "egyptian":
        if target == "egyptian":
            result = hieroglyphize_phrase(text)
            return {"ok": True, "mode": "script_render", "source": text, "target_language": target, **result, "confidence": 0.85}
        result = egyptian_to_modern(text, target, context)
        result["intent_analysis"] = detected_intent
        return result

    if target != "egyptian":
        exact = translate_word(text, source, target)
        if exact.get("ok"):
            exact["context"] = context
            exact["requested_intent"] = effective_intent
            exact["intent_analysis"] = detected_intent
            return exact
        return {
            **exact,
            "message": "Direct English↔Swahili general translation is outside the historical core. Use the device/browser language engine or a configured AI provider for unrestricted modern-language translation.",
        }

    exact = translate_word(text, source, "egyptian")
    if exact.get("ok") and exact.get("exact_match"):
        exact["context"] = context
        exact["requested_intent"] = effective_intent
        exact["intent_analysis"] = detected_intent
        exact["requested_mode"] = mode
        return exact
    result = translate_phrase(text, source, context, effective_intent)
    result["intent_analysis"] = detected_intent
    result["requested_mode"] = mode
    return result
