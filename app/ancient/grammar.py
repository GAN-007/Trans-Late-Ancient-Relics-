"""Sentence realizers for the Ancient Language Ladder.

A *frame* is the language-neutral meaning produced by a parser:

    {"kind": "clause", "subject": {"person": "1s"} | {"person": "3ms", "noun": "king", "adj": None},
     "verb": "trust", "tense": "past" | "present",
     "object": {"noun": "truth", "adj": None, "definite": True} | None}
    {"kind": "identity", "subject": {"person": "1s"}, "predicate": {"noun": "king", "adj": "good"}}
    {"kind": "np", "np": {"noun": "house", "adj": "great", "definite": True}}
    {"kind": "word", "word_kind": "noun" | "adj" | "verb", "concept": "truth"}

Each realizer turns a frame into tokens with per-token provenance, then into
transliteration plus every native script the language actually used. Where a
language lacks a word, the gap is reported instead of invented.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from . import scripts
from .lexicon import CONFIDENCE_SCORE, LATIN_PERSON_INDEX, PERSONS, entry, form, swahili_adjective

THIRD = {"3ms", "3fs"}


@dataclass
class Token:
    text: str
    info: dict[str, Any]
    conf: str = "high"
    flags: dict[str, Any] = field(default_factory=dict)

    @property
    def is_gap(self) -> bool:
        return self.info.get("type") == "gap"


def gap(kind: str, concept: str) -> Token:
    return Token(f"[{concept}]", {"type": "gap", "kind": kind, "concept": concept}, conf="low")


def subject_person(subject: dict[str, Any] | None) -> str:
    if not subject:
        return "3ms"
    return subject.get("person", "3ms")


class Realizer:
    id = "base"
    name = "Base"
    status = "attested"
    period = ""
    family = ""
    writing = ""
    order = ""
    notes: list[str] = []
    sentence_cap = 0.75

    # ----- overridable pieces -------------------------------------------------
    def np(self, spec: dict[str, Any], role: str, verb: str | None = None) -> list[Token]:
        raise NotImplementedError

    def verb(self, verb: str, person: str, tense: str, subject_noun: dict[str, Any] | None = None) -> list[Token]:
        raise NotImplementedError

    def citation_verb(self, verb: str) -> list[Token]:
        raise NotImplementedError

    def adjective_word(self, adj: str) -> list[Token]:
        return self.np({"noun": None, "adj": adj, "definite": False}, "citation")

    def clause(self, frame: dict[str, Any]) -> list[Token]:
        raise NotImplementedError

    def identity(self, frame: dict[str, Any]) -> list[Token]:
        raise NotImplementedError

    def render_scripts(self, tokens: list[Token]) -> dict[str, str]:
        return {}

    def joiner(self) -> str:
        return " "

    # ----- shared machinery --------------------------------------------------
    def tokens_for(self, frame: dict[str, Any]) -> list[Token]:
        kind = frame.get("kind")
        if kind == "clause":
            return self.clause(frame)
        if kind == "identity":
            return self.identity(frame)
        if kind == "np":
            return self.np(frame["np"], "citation")
        if kind == "word":
            if frame["word_kind"] == "noun":
                return self.np({"noun": frame["concept"], "adj": None, "definite": False}, "citation")
            if frame["word_kind"] == "adj":
                return self.adjective_word(frame["concept"])
            return self.citation_verb(frame["concept"])
        return []

    def realize(self, frame: dict[str, Any]) -> dict[str, Any]:
        self._refusal = None
        tokens = self.tokens_for(frame)
        refusal = getattr(self, "_refusal", None)
        self._refusal = None
        text = self.joiner().join(t.text for t in tokens if t.text)
        gaps = [t.info for t in tokens if t.is_gap]
        real = [t for t in tokens if not t.is_gap]
        confidence = min((CONFIDENCE_SCORE.get(t.conf, 0.45) for t in real), default=0.0)
        multiword = frame.get("kind") in {"clause", "identity"} or len(real) > 1
        status = "composed" if multiword else self.status
        if self.status == "reconstructed":
            confidence = min(confidence, 0.5)
            status = "reconstructed_composition" if multiword else "reconstructed"
        if self.status == "hypothetical":
            confidence = min(confidence, 0.15)
            status = "hypothetical"
        if multiword:
            confidence = min(confidence, self.sentence_cap)
        if gaps:
            confidence = round(confidence * 0.5, 2)
        result: dict[str, Any] = {
            "language": self.id,
            "language_name": self.name,
            "ok": bool(real) and not gaps and not refusal,
            "text": text,
            "scripts": {} if not real else self.render_scripts(tokens),
            "status": status if real else "unavailable",
            "confidence": round(confidence, 2) if real else 0.0,
            "tokens": [{"text": t.text, **t.info, "confidence": t.conf} for t in tokens],
            "gaps": gaps,
            "notes": list(dict.fromkeys(n for t in tokens for n in t.flags.get("notes", []))),
        }
        if refusal:
            result["refusal"] = refusal
            result["status"] = "not_attested_for_this_structure"
        return result


# ======================================================================= English
class English(Realizer):
    id, name, status = "english", "English", "attested"
    period, family, writing, order = "Modern", "Indo-European (Germanic)", "Latin alphabet", "SVO"
    PRON = {"1s": "I", "2ms": "you", "2fs": "you", "3ms": "he", "3fs": "she", "1p": "we", "2p": "you", "3p": "they"}
    COP = {"1s": "am", "3ms": "is", "3fs": "is"}

    def _noun(self, concept: str) -> str:
        return entry("noun", concept)["en"][0]

    def np(self, spec, role, verb=None):
        words: list[str] = []
        if spec.get("adj"):
            words.append(entry("adj", spec["adj"])["en"][0])
        if spec.get("noun"):
            words.append(self._noun(spec["noun"]))
        if role != "citation" or spec.get("definite"):
            if spec.get("definite", True):
                words.insert(0, "the")
            elif words:
                words.insert(0, "an" if words[0][0] in "aeiou" else "a")
        info = {"type": "np", "concept": spec.get("noun"), "adj": spec.get("adj")}
        return [Token(" ".join(words), info)]

    def verb(self, verb, person, tense, subject_noun=None):
        en = entry("verb", verb)["en"]
        if tense == "past":
            word = en["past"]
        else:
            word = en["s3"] if person in THIRD else en["base"]
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense})]

    def citation_verb(self, verb):
        return [Token("to " + entry("verb", verb)["en"]["base"], {"type": "verb", "verb": verb})]

    def adjective_word(self, adj):
        return [Token(entry("adj", adj)["en"][0], {"type": "adj", "concept": adj})]

    def _subject(self, subject):
        if subject.get("noun"):
            return self.np({"noun": subject["noun"], "adj": subject.get("adj"), "definite": True}, "subject")
        return [Token(self.PRON[subject["person"]], {"type": "pron", "person": subject["person"]})]

    def clause(self, frame):
        subject = frame["subject"]
        tokens = self._subject(subject) + self.verb(frame["verb"], subject_person(subject), frame["tense"])
        if frame.get("object"):
            prep = entry("verb", frame["verb"])["en"].get("prep")
            if prep:
                tokens.append(Token(prep, {"type": "prep"}))
            tokens += self.np(frame["object"], "object")
        tokens[0].text = tokens[0].text[:1].upper() + tokens[0].text[1:]
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        tokens = [Token(self.PRON[person], {"type": "pron", "person": person}),
                  Token(self.COP.get(person, "are"), {"type": "cop", "person": person})]
        tokens += self.np({**frame["predicate"], "definite": False}, "predicate")
        tokens[0].text = tokens[0].text[:1].upper() + tokens[0].text[1:]
        return tokens


# ======================================================================= Swahili
class Swahili(Realizer):
    id, name, status = "swahili", "Swahili", "attested"
    period, family, writing, order = "Modern", "Niger-Congo (Bantu)", "Latin alphabet", "SVO"
    SP = {"1s": "ni", "2ms": "u", "2fs": "u", "3ms": "a", "3fs": "a", "1p": "tu", "2p": "m", "3p": "wa"}
    PRON = {"1s": "mimi", "2ms": "wewe", "2fs": "wewe", "3ms": "yeye", "3fs": "yeye", "1p": "sisi", "2p": "ninyi", "3p": "wao"}
    TENSE = {"past": "li", "present": "na"}
    LOCATIVE_VERBS = {"go", "come", "live"}

    def np(self, spec, role, verb=None):
        tokens: list[Token] = []
        noun = form("noun", spec["noun"], "sw") if spec.get("noun") else None
        if noun:
            word = noun["f"]
            if role == "object" and verb in self.LOCATIVE_VERBS:
                word = word + "ni"
            tokens.append(Token(word, {"type": "noun", "concept": spec["noun"], "role": role}))
        if spec.get("adj"):
            stem = entry("adj", spec["adj"])["sw"]
            prefix = noun["ap"] if noun else "n"
            tokens.append(Token(swahili_adjective(stem, prefix), {"type": "adj", "concept": spec["adj"]}))
        return tokens

    def verb(self, verb, person, tense, subject_noun=None):
        sw = entry("verb", verb)["sw"]
        prefix = self.SP[person]
        if subject_noun:
            prefix = form("noun", subject_noun["noun"], "sw")["sp"]
        word = prefix + self.TENSE[tense] + ("ku" if sw.get("ku") else "") + sw["root"]
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense})]

    def citation_verb(self, verb):
        return [Token("ku" + entry("verb", verb)["sw"]["root"], {"type": "verb", "verb": verb})]

    def adjective_word(self, adj):
        return [Token("-" + entry("adj", adj)["sw"], {"type": "adj", "concept": adj})]

    def clause(self, frame):
        subject = frame["subject"]
        tokens: list[Token] = []
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        tokens += self.verb(frame["verb"], subject_person(subject), frame["tense"], subject if subject.get("noun") else None)
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        tokens[0].text = tokens[0].text[:1].upper() + tokens[0].text[1:]
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        tokens = [Token(self.PRON[person], {"type": "pron", "person": person}), Token("ni", {"type": "cop", "person": person})]
        tokens += self.np(frame["predicate"], "predicate")
        tokens[0].text = tokens[0].text[:1].upper() + tokens[0].text[1:]
        return tokens


# ===================================================================== Sumerian
class Sumerian(Realizer):
    id, name, status = "archaic_sumerian", "Archaic Sumerian", "attested"
    period = "Early Dynastic IIIa, c. 2600-2500 BCE (Abu Salabikh / Fara)"
    family, writing, order = "Language isolate", "Cuneiform", "SOV, ergative"
    notes = ["Earliest literary Sumerian (Kesh Temple Hymn, Instructions of Shuruppak) leaves most grammatical affixes unwritten; affixes here follow the fuller later standard so the meaning stays explicit."]
    PERFECTIVE_TRANS = {"1s": "mu-{R}", "2ms": "mu-e-{R}", "2fs": "mu-e-{R}", "3ms": "mu-un-{R}", "3fs": "mu-un-{R}",
                        "1p": "mu-{R}-en-de3-en", "2p": "mu-{R}-en-ze2-en", "3p": "mu-un-{R}-eš"}
    PERFECTIVE_INTRANS = {"1s": "{P}-{R}-en", "2ms": "{P}-{R}-en", "2fs": "{P}-{R}-en", "3ms": "{P}-{R}", "3fs": "{P}-{R}",
                          "1p": "{P}-{R}-en-de3-en", "2p": "{P}-{R}-en-ze2-en", "3p": "{P}-{R}-eš"}
    IMPERFECTIVE = {"1s": "i3-{R}-en", "2ms": "i3-{R}-en", "2fs": "i3-{R}-en", "3ms": "i3-{R}-e", "3fs": "i3-{R}-e",
                    "1p": "i3-{R}-en-de3-en", "2p": "i3-{R}-en-ze2-en", "3p": "i3-{R}-e-ne"}
    COPULA = {"1s": "me-en", "2ms": "me-en", "2fs": "me-en", "3ms": "am3", "3fs": "am3", "1p": "me-en-de3-en", "2p": "me-en-ze2-en", "3p": "me-eš"}

    @staticmethod
    def _pieces(translit: str, signs: list[str]) -> list[tuple[str, list[str]]]:
        parts = translit.split("-")
        if len(parts) == len(signs):
            return [(p, [s]) for p, s in zip(parts, signs)]
        return [(translit, signs)]

    @staticmethod
    def _affix(syllables: list[str]) -> list[tuple[str, list[str]]]:
        return [(s, [scripts.SUMERIAN_AFFIX_SIGNS[s]]) for s in syllables if s]

    def _token(self, pieces: list[tuple[str, list[str]]], info: dict, conf: str, notes: list[str] | None = None) -> Token:
        text = "-".join(p for p, _ in pieces).replace("- ", " ").replace(" -", " ")
        return Token(text, info, conf, {"pieces": pieces, "notes": notes or []})

    def np(self, spec, role, verb=None):
        tokens: list[Token] = []
        if spec.get("noun"):
            n = form("noun", spec["noun"], "sux")
            if not n:
                return [gap("noun", spec["noun"])]
            tokens.append(self._token(self._pieces(n["f"], n["signs"]), {"type": "noun", "concept": spec["noun"], "role": role}, n.get("c", "high")))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "sux")
            tokens.append(self._token(self._pieces(a["f"], a["signs"]), {"type": "adj", "concept": spec["adj"]}, a.get("c", "high")))
        case = None
        if role == "subject_erg":
            case = "e"
        elif role == "object" and verb:
            case = (form("verb", verb, "sux") or {}).get("obj_case")
        if case and tokens:
            last = tokens[-1]
            pieces = last.flags["pieces"] + self._affix([case])
            tokens[-1] = self._token(pieces, {**last.info, "case": case}, last.conf, last.flags.get("notes"))
        return tokens

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "sux")
        if not v:
            return [gap("verb", verb)]
        if tense == "present":
            root, signs, template = v.get("maru", v["root"]), v.get("maru_signs", v["signs"]), self.IMPERFECTIVE[person]
        else:
            root, signs = v["root"], v["signs"]
            template = self.PERFECTIVE_TRANS[person] if v.get("trans") else self.PERFECTIVE_INTRANS[person]
        pieces: list[tuple[str, list[str]]] = []
        if v.get("pre"):
            pieces.append((v["pre"] + " ", v["pre_signs"]))
        for part in template.split("-"):
            if part == "{R}":
                pieces.append((root, signs))
            elif part == "{P}":
                pieces += self._affix([v.get("prefix", "mu")])
            else:
                pieces += self._affix([part])
        notes = [v["note"]] if v.get("note") else []
        if tense == "present":
            notes.append("Imperfective (marû) forms are given with the regular suffix set; some verbs had irregular marû stems.")
        return [self._token(pieces, {"type": "verb", "verb": verb, "person": person, "tense": tense}, v.get("c", "medium"), notes)]

    def citation_verb(self, verb):
        v = form("verb", verb, "sux")
        if not v:
            return [gap("verb", verb)]
        pieces = ([(v["pre"] + " ", v["pre_signs"])] if v.get("pre") else []) + [(v["root"], v["signs"])]
        return [self._token(pieces, {"type": "verb", "verb": verb}, v.get("c", "medium"), [v["note"]] if v.get("note") else [])]

    def clause(self, frame):
        subject, verb = frame["subject"], frame["verb"]
        v = form("verb", verb, "sux") or {}
        tokens: list[Token] = []
        if subject.get("noun"):
            tokens += self.np(subject, "subject_erg" if v.get("trans") else "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", verb)
        tokens += self.verb(verb, subject_person(subject), frame["tense"])
        return tokens

    def identity(self, frame):
        tokens = self.np(frame["predicate"], "predicate")
        if tokens and not tokens[-1].is_gap:
            last = tokens[-1]
            pieces = last.flags["pieces"] + self._affix(self.COPULA[frame["subject"]["person"]].split("-"))
            tokens[-1] = self._token(pieces, {**last.info, "copula": frame["subject"]["person"]}, last.conf)
        return tokens

    def render_scripts(self, tokens):
        words = []
        for t in tokens:
            if t.is_gap:
                words.append("[…]")
                continue
            glyphs = []
            for translit, signs in t.flags["pieces"]:
                glyphs.append(scripts.cuneiform(signs) + (" " if translit.endswith(" ") else ""))
            words.append("".join(glyphs))
        return {"cuneiform": " ".join(words)}


# ===================================================================== Old Latin
class OldLatin(Realizer):
    id, name, status = "old_latin", "Old Latin", "attested"
    period = "c. 600-150 BCE (Lapis Niger, Duenos vase, Praeneste fibula, Scipio epitaphs)"
    family, writing, order = "Indo-European (Italic)", "Archaic Latin alphabet (Old Italic letterforms)", "SOV"
    notes = ["Old Latin is attested only in short inscriptions; sentences are composed in archaic orthography from attested forms and regular sound-spelling rules."]
    COP = ["esom", "es", "est", "somos", "estis", "sont"]
    CASES = {"nom": 0, "acc": 1, "dat": 2}

    @staticmethod
    def ablative(dative: str) -> str:
        for end, repl in (("oi", "od"), ("ai", "ad"), ("ei", "e"), ("ui", "u")):
            if dative.endswith(end):
                return dative[: -len(end)] + repl
        return dative

    def _noun_case(self, n: dict, case: str) -> str:
        if case == "abl":
            return self.ablative(n["dat"])
        return n[case]

    def _adj_case(self, a: dict, gender: str, case: str) -> str:
        forms = a.get(gender, a["m"])
        if case == "abl":
            return self.ablative(forms[2])
        return forms[self.CASES[case]]

    def np(self, spec, role, verb=None):
        case = {"subject": "nom", "predicate": "nom", "citation": "nom"}.get(role, "acc")
        prep = None
        if role == "object" and verb:
            obj = (form("verb", verb, "la") or {}).get("obj", "acc")
            case, prep = {"acc": ("acc", None), "dat": ("dat", None), "ad": ("acc", "ad"), "in": ("abl", "in")}[obj]
        tokens: list[Token] = []
        if prep:
            tokens.append(Token(prep, {"type": "prep"}))
        gender = "m"
        if spec.get("noun"):
            n = form("noun", spec["noun"], "la")
            if not n:
                return [gap("noun", spec["noun"])]
            gender = n["g"]
            notes = [n["note"]] if n.get("note") else []
            notes.append(f"Classical Latin: {n['cl']}")
            tokens.append(Token(self._noun_case(n, case), {"type": "noun", "concept": spec["noun"], "role": role, "case": case}, n.get("c", "high"), {"notes": notes}))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "la")
            notes = [a["note"]] if a.get("note") else []
            tokens.append(Token(self._adj_case(a, gender, case), {"type": "adj", "concept": spec["adj"], "case": case}, a.get("c", "high"), {"notes": notes}))
        return tokens

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "la")
        if not v:
            return [gap("verb", verb)]
        word = v["perf" if tense == "past" else "pres"][LATIN_PERSON_INDEX[person]]
        notes = [f"Classical Latin: {v['cl']}"] + ([v["note"]] if v.get("note") else [])
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense}, v.get("c", "high"), {"notes": notes})]

    def citation_verb(self, verb):
        v = form("verb", verb, "la")
        if not v:
            return [gap("verb", verb)]
        return [Token(v["pres"][0], {"type": "verb", "verb": verb}, v.get("c", "high"), {"notes": [f"Classical Latin: {v['cl']}"]})]

    def clause(self, frame):
        subject = frame["subject"]
        tokens: list[Token] = []
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        tokens += self.verb(frame["verb"], subject_person(subject), frame["tense"])
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        return self.np(frame["predicate"], "predicate") + [
            Token(self.COP[LATIN_PERSON_INDEX[person]], {"type": "cop", "person": person}, "medium", {"notes": ["ESOM is the archaic first-person form of later sum."]})
        ]

    def render_scripts(self, tokens):
        text = " ".join(t.text for t in tokens if not t.is_gap)
        return {"archaic_capitals": scripts.latin_capitals(text), "old_italic": scripts.old_italic(text)}


# ===================================================================== Old Arabic
class OldArabic(Realizer):
    id, name, status = "old_arabic", "Old Arabic (pre-Islamic)", "attested"
    period = "c. 1st century BCE - 6th century CE (Safaitic, Hismaic, Nabataeo-Arabic, Namara 328 CE)"
    family, writing, order = "Afro-Asiatic (Semitic, Central)", "Ancient North Arabian (Safaitic) and early undotted Arabic script", "VSO"
    notes = ["Pre-Islamic inscriptions write consonants only; the vocalized transliteration uses Classical Arabic morphology to make the reading explicit."]
    PRON = {"1s": "ʾanā", "2ms": "ʾanta", "2fs": "ʾanti", "3ms": "huwa", "3fs": "hiya", "1p": "naḥnu", "2p": "ʾantum", "3p": "hum"}
    PERF_END = {"1s": ("c", "tu"), "2ms": ("c", "ta"), "2fs": ("c", "ti"), "3ms": ("v", "a"), "3fs": ("v", "at"), "1p": ("c", "nā"), "2p": ("c", "tum"), "3p": ("v", "ū")}
    IMPF = {"1s": ("ʾ", ""), "2ms": ("t", ""), "2fs": ("t", "īna"), "3ms": ("y", ""), "3fs": ("t", ""), "1p": ("n", ""), "2p": ("t", "ūna"), "3p": ("y", "ūna")}
    CASE_END = {"nom": "u", "acc": "a", "gen": "i"}
    CLITIC_PREPS = {"bi"}

    def _noun_word(self, stem: str, case: str, definite: bool, elided: bool) -> str:
        if definite:
            article = scripts.arabic_article_elided(stem) if elided else scripts.arabic_article(stem)
            return article + stem + self.CASE_END[case]
        return stem + self.CASE_END[case] + "n"

    def np(self, spec, role, verb=None):
        case = {"subject": "nom", "predicate": "nom", "citation": "nom"}.get(role, "acc")
        prep = None
        if role == "object" and verb:
            prep = (form("verb", verb, "ar") or {}).get("prep")
            if prep:
                case = "gen"
        definite = spec.get("definite", True) and role != "predicate"
        if role == "citation":
            definite = spec.get("definite", False)
        tokens: list[Token] = []
        gender = "m"
        if spec.get("noun"):
            n = form("noun", spec["noun"], "ar")
            if not n:
                return [gap("noun", spec["noun"])]
            gender = n["g"]
            if prep in self.CLITIC_PREPS:
                word = prep + "-" + self._noun_word(n["f"], case, definite, elided=True)
            else:
                if prep:
                    tokens.append(Token(prep, {"type": "prep"}))
                word = self._noun_word(n["f"], case, definite, elided=bool(prep))
            tokens.append(Token(word, {"type": "noun", "concept": spec["noun"], "role": role, "case": case}, n.get("c", "high"), {"fem_noun": n["f"].endswith("at")}))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "ar")
            stem = a["f"] + ("at" if gender == "f" else "")
            word = self._noun_word(stem, case, definite, elided=bool(spec.get("noun")))
            tokens.append(Token(word, {"type": "adj", "concept": spec["adj"], "case": case}, a.get("c", "high"), {"fem_noun": gender == "f"}))
        return tokens

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "ar")
        if not v:
            return [gap("verb", verb)]
        if tense == "past":
            p = v["perf"]
            if person in p:
                word = p[person]
            else:
                stem_kind, ending = self.PERF_END[person]
                word = p[stem_kind] + ending
        else:
            i = v["impf"]
            index = PERSONS.index(person)
            if "list" in i:
                word = i["list"][index]
            elif person in i:
                word = i[person]
            else:
                prefix, suffix = self.IMPF[person]
                word = prefix + i["pv"] + i["stem"] + (suffix or "u")
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense}, v.get("c", "high"),
                      {"plural_verb": tense == "past" and person == "3p"})]

    def citation_verb(self, verb):
        return self.verb(verb, "3ms", "past")

    def clause(self, frame):
        subject = frame["subject"]
        person = subject_person(subject)
        if subject.get("noun"):
            n = form("noun", subject["noun"], "ar")
            person = "3fs" if n and n["g"] == "f" else "3ms"
        tokens = self.verb(frame["verb"], person, frame["tense"])
        if subject.get("noun"):
            tokens += self.np({**subject, "definite": True}, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        return [Token(self.PRON[person], {"type": "pron", "person": person})] + self.np({**frame["predicate"], "definite": False}, "predicate")

    def render_scripts(self, tokens):
        items = [{"text": t.text, **{k: v for k, v in t.flags.items() if k in {"fem_noun", "plural_verb"}}} for t in tokens if not t.is_gap]
        return {
            "safaitic": scripts.safaitic(items),
            "early_arabic_rasm": scripts.arabic_rasm(items),
            "arabic_unvocalized": scripts.arabic_dotted(items),
        }


# ======================================================================= Ge'ez
class Geez(Realizer):
    id, name, status = "geez", "Ge'ez (Classical Ethiopic)", "attested"
    period = "Aksumite inscriptions from c. 4th century CE (Ezana); oldest vocalized texts"
    family, writing, order = "Afro-Asiatic (Semitic, Ethio-Semitic)", "Ge'ez fidel (abugida)", "VSO (also SVO)"
    PRON = {"1s": "ʾana", "2ms": "ʾanta", "2fs": "ʾanti", "3ms": "wəʾətu", "3fs": "yəʾəti", "1p": "nəḥna", "2p": "ʾantəmmu", "3p": "wəʾətomu"}
    PERF_END = {"1s": ("c", "ku"), "2ms": ("c", "ka"), "2fs": ("c", "ki"), "3ms": ("v", "a"), "3fs": ("v", "at"), "1p": ("c", "na"), "2p": ("c", "kəmmu"), "3p": ("v", "u")}
    IMPF = {"1s": ("ʾ", ""), "2ms": ("t", ""), "2fs": ("t", "i"), "3ms": ("y", ""), "3fs": ("t", ""), "1p": ("n", ""), "2p": ("t", "u"), "3p": ("y", "u")}
    CLITIC_PREPS = {"ba"}

    def np(self, spec, role, verb=None):
        accusative = role == "object"
        prep = None
        if role == "object" and verb:
            prep = (form("verb", verb, "gez") or {}).get("prep")
            if prep:
                accusative = False
        tokens: list[Token] = []
        if spec.get("noun"):
            n = form("noun", spec["noun"], "gez")
            if not n:
                return [gap("noun", spec["noun"])]
            word = n.get("acc", n["f"] + "a") if accusative else n["f"]
            if prep in self.CLITIC_PREPS:
                word = prep + "-" + word
            elif prep:
                tokens.append(Token(prep, {"type": "prep"}))
            tokens.append(Token(word, {"type": "noun", "concept": spec["noun"], "role": role}, n.get("c", "high")))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "gez")
            tokens.append(Token(a["f"] + ("a" if accusative else ""), {"type": "adj", "concept": spec["adj"]}, a.get("c", "high")))
        return tokens

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "gez")
        if not v:
            return [gap("verb", verb)]
        if tense == "past":
            stem_kind, ending = self.PERF_END[person]
            word = v["perf"][stem_kind] + ending
        else:
            prefix, suffix = self.IMPF[person]
            stem = v["impf"]["stem"]
            if suffix and stem[-1] in "iu":
                # weak final radical resurfaces before a vowel: yəsatti -> yəsattəyu, yəḥayyu -> yəḥayyəwu
                stem = stem[:-1] + "ə" + ("y" if stem[-1] == "i" else "w")
            word = prefix + v["impf"]["pv"] + stem + suffix
        notes = [] if tense == "past" else ["Ge'ez imperfect stems vary by verb type; present forms are lower confidence than perfects."]
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense}, v.get("c", "high") if tense == "past" else "medium", {"notes": notes})]

    def citation_verb(self, verb):
        return self.verb(verb, "3ms", "past")

    def clause(self, frame):
        subject = frame["subject"]
        person = subject_person(subject)
        if subject.get("noun"):
            n = form("noun", subject["noun"], "gez")
            person = "3fs" if n and n["g"] == "f" else "3ms"
        tokens = self.verb(frame["verb"], person, frame["tense"])
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        return [Token(self.PRON[person], {"type": "pron", "person": person})] + self.np(frame["predicate"], "predicate")

    def render_scripts(self, tokens):
        return {"fidel": scripts.ethiopic([w for t in tokens if not t.is_gap for w in t.text.split()])}


# ===================================================================== Old Amharic
class OldAmharic(Realizer):
    id, name, status = "old_amharic", "Old Amharic", "attested"
    period = "Earliest texts: 14th-century royal praise songs (Amda Seyon); grammar shown in its conservative written form"
    family, writing, order = "Afro-Asiatic (Semitic, Ethio-Semitic)", "Ge'ez fidel with Amharic letters", "SOV"
    notes = ["Old Amharic survives in a handful of 14th-16th century songs; forms are given in conservative Amharic orthography, which is close to that stage."]
    PRON = {"1s": "ʾəne", "2ms": "ʾantä", "2fs": "ʾanči", "3ms": "ʾərsu", "3fs": "ʾərswa", "1p": "ʾəñña", "2p": "ʾənnantä", "3p": "ʾənnärsu"}
    COP = {"1s": "nəññ", "2ms": "nəh", "2fs": "nəš", "3ms": "näw", "3fs": "nat", "1p": "nän", "2p": "naččəhu", "3p": "naččäw"}
    IMPF = {"1s": ("ʾə", "allähu"), "2ms": ("tə", "alläh"), "2fs": ("tə", "iyalläš"), "3ms": ("yə", "al"), "3fs": ("tə", "alläčč"),
            "1p": ("ʾənnə", "allän"), "2p": ("tə", "allaččəhu"), "3p": ("yə", "allu")}
    CLITIC_PREPS = {"bä"}

    @staticmethod
    def _definite(word: str, feminine: bool) -> str:
        if feminine:
            return word + "wa"
        return word + ("w" if word[-1] in "aäeiouə" else "u")

    def np(self, spec, role, verb=None):
        prep = (form("verb", verb, "am") or {}).get("prep") if role == "object" and verb else None
        definite = spec.get("definite", True) and role not in {"predicate", "citation"} and not prep
        accusative = role == "object" and definite
        noun = form("noun", spec["noun"], "am") if spec.get("noun") else None
        if spec.get("noun") and not noun:
            return [gap("noun", spec["noun"])]
        words: list[tuple[str, dict, str]] = []
        if spec.get("adj"):
            a = form("adj", spec["adj"], "am")
            words.append((a["f"], {"type": "adj", "concept": spec["adj"]}, a.get("c", "high")))
        if noun:
            words.append((noun["f"], {"type": "noun", "concept": spec["noun"], "role": role}, noun.get("c", "high")))
        if definite and words:
            first, info, conf = words[0]
            first = self._definite(first, bool(noun and noun["g"] == "f"))
            if accusative:
                first += "n"
            words[0] = (first, info, conf)
        tokens: list[Token] = []
        if prep and prep not in self.CLITIC_PREPS:
            tokens.append(Token(prep, {"type": "prep"}))
        for index, (word, info, conf) in enumerate(words):
            if index == 0 and prep in self.CLITIC_PREPS:
                word = prep + "-" + word
            tokens.append(Token(word, info, conf))
        return tokens

    def _imperfect(self, stem: str, person: str) -> str:
        prefix, suffix = self.IMPF[person]
        if stem.startswith("ʾ") and len(stem) > 1 and stem[1] in "aäeiouə":
            prefix, stem = prefix[:-1], stem[1:]  # yə + ʾamn -> yamn
            if prefix == "ʾ":
                prefix = "ʾ"
        if stem[-1] in "aä" and suffix[0] in "ai":
            stem = stem[:-1]
        return prefix + stem + suffix

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "am")
        if not v:
            return [gap("verb", verb)]
        if tense == "past":
            return [Token(v["perf"][PERSONS.index(person)], {"type": "verb", "verb": verb, "person": person, "tense": tense}, v.get("c", "high"),
                          {"notes": ["Old Amharic and Ge'ez use -ku for 'I'; later Amharic also writes -hu after vowels."] if person == "1s" else []})]
        word = self._imperfect(v["impf"], person)
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense}, "medium",
                      {"notes": ["The compound imperfect (-al/-allähu) is the modern present; its earliest attestation post-dates the 14th-century songs."]})]

    def citation_verb(self, verb):
        return self.verb(verb, "3ms", "past")

    def clause(self, frame):
        subject = frame["subject"]
        person = subject_person(subject)
        tokens: list[Token] = []
        if subject.get("noun"):
            n = form("noun", subject["noun"], "am")
            person = "3fs" if n and n["g"] == "f" else "3ms"
            tokens += self.np({**subject, "definite": True}, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        tokens += self.verb(frame["verb"], person, frame["tense"])
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        return ([Token(self.PRON[person], {"type": "pron", "person": person})]
                + self.np(frame["predicate"], "predicate")
                + [Token(self.COP[person], {"type": "cop", "person": person})])

    def render_scripts(self, tokens):
        return {"fidel": scripts.ethiopic([w for t in tokens if not t.is_gap for w in t.text.split()], amharic=True)}


# ================================================================= Proto-Semitic
class ProtoSemitic(Realizer):
    id, name, status = "proto_semitic", "Proto-Semitic", "reconstructed"
    period = "Reconstructed ancestor, c. 4000 BCE or earlier (never written)"
    family, writing, order = "Afro-Asiatic (Semitic)", "None - reconstruction notation only", "VSO (reconstructed)"
    notes = ["Every form is reconstructed by the comparative method from Akkadian, Hebrew, Aramaic, Arabic, Ge'ez and others. No text in Proto-Semitic exists.",
             "Suffix-conjugation endings follow the Ethio-Semitic k-series (1sg *-ku), which many reconstructions treat as original; Arabic and Hebrew levelled them to -t-."]
    PRON = {"1s": "ʔanāku", "2ms": "ʔanta", "2fs": "ʔanti", "3ms": "šuʔa", "3fs": "šiʔa", "1p": "niḥnū", "2p": "ʔantumū", "3p": "šumū"}
    PERF_END = {"1s": "ku", "2ms": "ka", "2fs": "ki", "3ms": "a", "3fs": "at", "1p": "nū", "2p": "kunū", "3p": "ū"}
    IMPF = {"1s": ("ʔa", ""), "2ms": ("ta", ""), "2fs": ("ta", "ī"), "3ms": ("ya", ""), "3fs": ("ta", ""), "1p": ("na", ""), "2p": ("ta", "ū"), "3p": ("ya", "ū")}
    CASE_END = {"nom": "u", "acc": "a", "gen": "i"}

    def np(self, spec, role, verb=None):
        case = {"subject": "nom", "predicate": "nom", "citation": "nom"}.get(role, "acc")
        prep = (form("verb", verb, "sem") or {}).get("prep") if role == "object" and verb else None
        if prep:
            case = "gen"
        tokens: list[Token] = []
        gender = "m"
        if spec.get("noun"):
            n = form("noun", spec["noun"], "sem")
            if not n:
                return [gap("noun", spec["noun"])]
            gender = n["g"]
            word = n["f"] + self.CASE_END[case]
            if prep:
                word = prep + "-" + word
            tokens.append(Token(word, {"type": "noun", "concept": spec["noun"], "role": role, "case": case}, n.get("c", "medium"), {"notes": [n["note"]] if n.get("note") else []}))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "sem")
            tokens.append(Token(a["f"] + ("at" if gender == "f" else "") + self.CASE_END[case], {"type": "adj", "concept": spec["adj"]}, a.get("c", "medium")))
        return tokens

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "sem")
        if not v:
            return [gap("verb", verb)]
        if tense == "past":
            word = v["perf"] + self.PERF_END[person]
        else:
            prefix, suffix = self.IMPF[person]
            word = prefix + v["impf"] + suffix
        return [Token(word, {"type": "verb", "verb": verb, "person": person, "tense": tense}, v.get("c", "low"), {"notes": [v["note"]] if v.get("note") else []})]

    def citation_verb(self, verb):
        return self.verb(verb, "3ms", "past")

    def clause(self, frame):
        subject = frame["subject"]
        person = subject_person(subject)
        if subject.get("noun"):
            n = form("noun", subject["noun"], "sem")
            person = "3fs" if n and n["g"] == "f" else "3ms"
        tokens = self.verb(frame["verb"], person, frame["tense"])
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        return [Token(self.PRON[person], {"type": "pron", "person": person}, "medium")] + self.np(frame["predicate"], "predicate")

    def tokens_for(self, frame):
        tokens = super().tokens_for(frame)
        for t in tokens:
            if not t.is_gap and not t.text.startswith("*"):
                t.text = "*" + t.text
        return tokens


# ==================================================================== Egyptian
class Egyptian(Realizer):
    status = "attested"
    family, writing, order = "Afro-Asiatic (Egyptian)", "Hieroglyphic", "VSO"
    SUFFIX = {"1s": "j", "2ms": "k", "2fs": "ṯ", "3ms": "f", "3fs": "s", "1p": "n", "2p": "ṯn", "3p": "sn"}
    PRON = {"1s": "jnk", "2ms": "ntk", "2fs": "ntṯ", "3ms": "ntf", "3fs": "nts", "1p": "jnn", "2p": "ntṯn", "3p": "ntsn"}
    merge_z = False

    def _form(self, text: str) -> str:
        return text.replace("z", "s") if self.merge_z else text

    def _glyphs(self, translit: str, gardiner: list[str] | None) -> str:
        if gardiner:
            try:
                return scripts.hieroglyphs(gardiner)
            except KeyError:
                pass
        from ..egyptian import hieroglyphize_word
        return hieroglyphize_word(translit)["hieroglyphs"]

    def np(self, spec, role, verb=None):
        tokens: list[Token] = []
        if role == "object" and verb:
            prep = (form("verb", verb, "egy") or {}).get("prep")
            if prep and not (form("verb", verb, "egy") or {}).get("pattern"):
                tokens.append(Token(prep, {"type": "prep"}, flags={"glyphs": self._glyphs(prep, None)}))
        gender = "m"
        if spec.get("noun"):
            n = form("noun", spec["noun"], "egy")
            if not n:
                return [gap("noun", spec["noun"])]
            gender = n.get("g", "m")
            word = self._form(n["f"])
            tokens.append(Token(word, {"type": "noun", "concept": spec["noun"], "role": role}, n.get("c", "high"), {"glyphs": self._glyphs(word, n.get("gl"))}))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "egy")
            word = a["f"] + ("t" if gender == "f" else "")
            glyphs = self._glyphs(a["f"], a.get("gl")) + (scripts.hieroglyph("X001") if gender == "f" else "")
            tokens.append(Token(word, {"type": "adj", "concept": spec["adj"]}, a.get("c", "high"), {"glyphs": glyphs}))
        return tokens

    def _suffix_glyphs(self, suffix: str) -> str:
        return scripts.hieroglyphs(scripts.EGYPTIAN_SUFFIX_GLYPHS[suffix])

    def verb(self, verb, person, tense, subject_noun=None):
        v = form("verb", verb, "egy")
        if not v:
            return [gap("verb", verb)]
        stem = self._form(v["perf"] if tense == "past" else v["pres"])
        glyphs = self._glyphs(stem, v.get("gl"))
        parts = [stem]
        if tense == "past":
            parts.append("n")
            glyphs += scripts.hieroglyphs(scripts.EGYPTIAN_PERFECT_N)
        if not subject_noun:
            suffix = self.SUFFIX[person]
            parts.append(suffix)
            glyphs += self._suffix_glyphs(suffix)
        notes = [v["note"]] if v.get("note") else []
        notes.append("sḏm.n.f perfect" if tense == "past" else "sḏm.f (circumstantial/present)")
        info = {"type": "verb", "verb": verb, "person": person, "tense": tense}
        if subject_noun:
            info["noun_subject"] = True
        return [Token(".".join(parts), info, v.get("c", "high"), {"glyphs": glyphs, "notes": notes})]

    def citation_verb(self, verb):
        v = form("verb", verb, "egy")
        if not v:
            return [gap("verb", verb)]
        stem = self._form(v["perf"])
        return [Token(stem, {"type": "verb", "verb": verb}, v.get("c", "high"), {"glyphs": self._glyphs(stem, v.get("gl"))})]

    def clause(self, frame):
        subject, verb = frame["subject"], frame["verb"]
        person = subject_person(subject)
        v = form("verb", verb, "egy") or {}
        tokens = self.verb(verb, person, frame["tense"], subject if subject.get("noun") else None)
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            if v.get("pattern") == "jb":
                suffix = self.SUFFIX[person]
                if subject.get("noun"):
                    n = form("noun", subject["noun"], "egy") or {}
                    suffix = "s" if n.get("g") == "f" else "f"
                tokens.append(Token(f"jb.{suffix}", {"type": "idiom", "verb": verb}, "low", {"glyphs": scripts.hieroglyphs(["F034", "Z001"]) + self._suffix_glyphs(suffix)}))
                tokens.append(Token(v["prep"], {"type": "prep"}, flags={"glyphs": scripts.hieroglyph("G017")}))
            tokens += self.np(frame["object"], "object", verb)
        return tokens

    def identity(self, frame):
        person = frame["subject"]["person"]
        pron = self.PRON[person]
        return [Token(pron, {"type": "pron", "person": person}, "high", {"glyphs": self._glyphs(pron, None)})] + self.np(frame["predicate"], "predicate")

    def render_scripts(self, tokens):
        return {"hieroglyphs": " ".join(t.flags.get("glyphs", "") for t in tokens if not t.is_gap).strip()}


class OldEgyptian(Egyptian):
    id, name = "old_egyptian", "Old Egyptian"
    period = "c. 2686-2160 BCE (Old Kingdom; Pyramid Texts, tomb autobiographies)"
    notes = ["Old Egyptian keeps z and s distinct and often leaves the 1st-person suffix .j unwritten."]


class MiddleEgyptian(Egyptian):
    id, name = "middle_egyptian", "Middle Egyptian"
    period = "c. 2055-1650 BCE classical stage (used in monuments much later)"
    merge_z = True
    notes = ["Middle Egyptian has merged Old Egyptian z into s."]


class ArchaicHieroglyphic(Egyptian):
    id, name = "archaic_hieroglyphic", "Archaic / proto-hieroglyphic Egyptian"
    period = "c. 3250-2700 BCE (Abydos tomb U-j labels, Naqada III, Early Dynastic seals)"
    sentence_cap = 0.2
    notes = ["The earliest Egyptian writing records names, places, titles and quantities. No continuous sentence is attested before the seal of Peribsen (c. 2690 BCE)."]

    def clause(self, frame):
        self._refusal = ("Archaic hieroglyphic writing does not record full verbal sentences; only a logographic label "
                         "of the content words is given.")
        tokens: list[Token] = []
        if frame["subject"].get("noun"):
            tokens += Egyptian.np(self, frame["subject"], "subject")
        if frame.get("object"):
            tokens += Egyptian.np(self, frame["object"], "label")
        if not tokens:
            tokens.append(Token("", {"type": "none"}))
        return [t for t in tokens if t.text]

    def identity(self, frame):
        self._refusal = "Pronoun-plus-noun sentences are not attested this early; the label shows the noun alone, as on Early Dynastic seals."
        return Egyptian.np(self, frame["predicate"], "label")

    def citation_verb(self, verb):
        self._refusal = "Archaic labels do not write verbs; no form is given."
        return [gap("verb", verb)]


# ================================================================== Proto-World
class ProtoWorld(Realizer):
    id, name, status = "proto_world", "Proto-World (hypothetical)", "hypothetical"
    period = "Hypothetical; if real, tens of thousands of years ago"
    family, writing, order = "Hypothetical ancestor of all languages", "None", "Unknown"
    notes = ["Proto-World roots were proposed by Bengtson & Ruhlen (1994). Most historical linguists reject them: beyond c. 8,000-10,000 years, chance resemblances swamp any inherited signal.",
             "No grammar has been proposed, so sentences cannot be built - only isolated roots."]

    def _root(self, concept: str) -> Token:
        r = form("noun", concept, "pw")
        if not r:
            return gap("noun", concept)
        return Token("*" + r["f"].upper(), {"type": "noun", "concept": concept}, "low", {"notes": [r["note"]]})

    def np(self, spec, role, verb=None):
        if spec.get("noun"):
            return [self._root(spec["noun"])]
        return [gap("adj", spec["adj"])]

    def citation_verb(self, verb):
        return [gap("verb", verb)]

    def adjective_word(self, adj):
        return [gap("adj", adj)]

    def clause(self, frame):
        self._refusal = "No Proto-World grammar has been proposed; only roots for the content words are listed."
        tokens = []
        if frame["subject"].get("noun"):
            tokens.append(self._root(frame["subject"]["noun"]))
        if frame.get("object"):
            tokens.append(self._root(frame["object"]["noun"]))
        return [t for t in tokens if not t.is_gap]

    def identity(self, frame):
        self._refusal = "No Proto-World grammar has been proposed; only the noun root is listed."
        return [self._root(frame["predicate"]["noun"])]


REALIZERS: dict[str, Realizer] = {
    r.id: r for r in (
        English(), Swahili(), Sumerian(), OldLatin(), OldArabic(), Geez(), OldAmharic(),
        ProtoSemitic(), ProtoWorld(), ArchaicHieroglyphic(), OldEgyptian(), MiddleEgyptian(),
    )
}


def loose_key(text: str) -> str:
    """Accent-, index- and separator-insensitive key used for matching user input."""
    text = unicodedata.normalize("NFC", text.lower()).replace("*", "")
    text = text.replace("ꜣ", "a").replace("ꜥ", "").replace("ə", "e").replace("ĝ", "g")
    for ch in "ʾʿʔʕ'’`":
        text = text.replace(ch, "")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    text = re.sub(r"[\d\-\.=_]", "", text)
    return text
