"""Sentence realizers for the Ancient Language Ladder.

A *frame* is the language-neutral meaning produced by a parser:

    {"kind": "clause", "subject": {"person": "1s"} | {"person": "3ms", "noun": "king", "adj": None},
     "verb": "trust", "tense": "past" | "present",
     "object": {"noun": "truth", "adj": None, "definite": True} | None,
     "negative": False, "question": False}
    {"kind": "identity", "subject": {"person": "1s"} | {"person": "3ms", "noun": "king"},
     "predicate": {"noun": "servant" | None, "adj": "good" | None}, "negative": False, "question": False}

A predicate with no noun is an adjective sentence ("the king is great").
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
PLURAL = {"1p", "2p", "3p"}
FEMININE = {"2fs", "3fs"}


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


def noun_gender(concept: str | None, lang: str) -> str:
    if not concept:
        return "m"
    return (form("noun", concept, lang) or {}).get("g", "m")


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

    question_note = ""  # how (or whether) the language marks a yes/no question

    @staticmethod
    def _punctuate(rendered: dict[str, str], question: bool) -> dict[str, str]:
        if not question:
            return rendered
        out = {}
        for name, value in rendered.items():
            if value.endswith("።"):
                out[name] = value[:-1] + "፧"  # Ethiopic question mark
            elif name.startswith("arabic"):
                out[name] = value + "؟"
            elif name == "cuneiform":
                out[name] = value + "?"  # Sumerian writing has no question marker; editorial, as in the transliteration
            else:
                out[name] = value
        return out

    def realize(self, frame: dict[str, Any]) -> dict[str, Any]:
        self._refusal = None
        tokens = self.tokens_for(frame)
        refusal = getattr(self, "_refusal", None)
        self._refusal = None
        text = self.joiner().join(t.text for t in tokens if t.text)
        question = bool(frame.get("question") and text)
        if question:
            text += "?"
            if self.question_note and tokens:
                tokens[-1].flags.setdefault("notes", []).append(self.question_note)
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
            "scripts": {} if not real else self._punctuate(self.render_scripts(tokens), question),
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

    @staticmethod
    def _capitalize(tokens):
        tokens[0].text = tokens[0].text[:1].upper() + tokens[0].text[1:]
        return tokens

    def clause(self, frame):
        subject = frame["subject"]
        person, tense = subject_person(subject), frame["tense"]
        negative, question = frame.get("negative"), frame.get("question")
        if negative or question:
            # do-support: "Did the king see…?", "The king did not see…"
            aux = Token("did" if tense == "past" else ("does" if person in THIRD else "do"), {"type": "aux"})
            main = Token(entry("verb", frame["verb"])["en"]["base"], {"type": "verb", "verb": frame["verb"], "person": person, "tense": tense})
            neg = [Token("not", {"type": "neg"})] if negative else []
            tokens = ([aux] + self._subject(subject) + neg + [main]) if question else (self._subject(subject) + [aux] + neg + [main])
        else:
            tokens = self._subject(subject) + self.verb(frame["verb"], person, tense)
        if frame.get("object"):
            prep = entry("verb", frame["verb"])["en"].get("prep")
            if prep:
                tokens.append(Token(prep, {"type": "prep"}))
            tokens += self.np(frame["object"], "object")
        return self._capitalize(tokens)

    def identity(self, frame):
        subject = frame["subject"]
        person = subject_person(subject)
        cop = Token("is" if subject.get("noun") else self.COP.get(person, "are"), {"type": "cop", "person": person})
        predicate = frame["predicate"]
        if predicate.get("noun"):
            pred = self.np({**predicate, "definite": False}, "predicate")
        else:
            pred = [Token(entry("adj", predicate["adj"])["en"][0], {"type": "adj", "concept": predicate["adj"], "role": "predicate"})]
        neg = [Token("not", {"type": "neg"})] if frame.get("negative") else []
        if frame.get("question"):
            tokens = [cop] + self._subject(subject) + neg + pred
        else:
            tokens = self._subject(subject) + [cop] + neg + pred
        return self._capitalize(tokens)


# ======================================================================= Swahili
class Swahili(Realizer):
    id, name, status = "swahili", "Swahili", "attested"
    period, family, writing, order = "Modern", "Niger-Congo (Bantu)", "Latin alphabet", "SVO"
    SP = {"1s": "ni", "2ms": "u", "2fs": "u", "3ms": "a", "3fs": "a", "1p": "tu", "2p": "m", "3p": "wa"}
    PRON = {"1s": "mimi", "2ms": "wewe", "2fs": "wewe", "3ms": "yeye", "3fs": "yeye", "1p": "sisi", "2p": "ninyi", "3p": "wao"}
    TENSE = {"past": "li", "present": "na"}
    NEG = {"1s": "si", "2ms": "hu", "2fs": "hu", "3ms": "ha", "3fs": "ha", "1p": "hatu", "2p": "ham", "3p": "hawa"}
    LOCATIVE_VERBS = {"go", "come", "live"}
    question_note = "Swahili marks a yes/no question with rising intonation; the opening Je is optional."

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

    def verb(self, verb, person, tense, subject_noun=None, negative=False):
        sw = entry("verb", verb)["sw"]
        info = {"type": "verb", "verb": verb, "person": person, "tense": tense}
        if negative:
            neg = self.NEG[person]
            if subject_noun:
                sp = form("noun", subject_noun["noun"], "sw")["sp"]
                neg = "ha" if sp == "a" else "ha" + sp
            if tense == "past":
                word = neg + ("kw" if sw["root"].startswith("e") else "ku") + sw["root"]  # hakuona, hakula, hakwenda
            else:
                root = sw["root"]
                stem = root[:-1] + "i" if root.endswith("a") else root  # haoni, hali, haamini
                word = (neg + "u" if neg == "ham" else neg) + stem
            return [Token(word, {**info, "negative": True})]
        prefix = self.SP[person]
        if subject_noun:
            prefix = form("noun", subject_noun["noun"], "sw")["sp"]
        word = prefix + self.TENSE[tense] + ("ku" if sw.get("ku") else "") + sw["root"]
        return [Token(word, info)]

    def citation_verb(self, verb):
        return [Token("ku" + entry("verb", verb)["sw"]["root"], {"type": "verb", "verb": verb})]

    def adjective_word(self, adj):
        return [Token("-" + entry("adj", adj)["sw"], {"type": "adj", "concept": adj})]

    def clause(self, frame):
        subject = frame["subject"]
        tokens: list[Token] = [Token("Je,", {"type": "q"})] if frame.get("question") else []
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        tokens += self.verb(frame["verb"], subject_person(subject), frame["tense"], subject if subject.get("noun") else None, frame.get("negative", False))
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        tokens[0].text = tokens[0].text[:1].upper() + tokens[0].text[1:]
        return tokens

    def identity(self, frame):
        subject, predicate = frame["subject"], frame["predicate"]
        person = subject_person(subject)
        tokens: list[Token] = [Token("Je,", {"type": "q"})] if frame.get("question") else []
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        else:
            tokens.append(Token(self.PRON[person], {"type": "pron", "person": person}))
        tokens.append(Token("si" if frame.get("negative") else "ni", {"type": "cop", "person": person, "negative": bool(frame.get("negative"))}))
        if predicate.get("noun"):
            tokens += self.np(predicate, "predicate")
        else:
            # the adjective agrees with the subject's noun class: mfalme ni mkubwa, jua ni kubwa, sisi ni wakubwa
            prefix = form("noun", subject["noun"], "sw")["ap"] if subject.get("noun") else ("wa" if person in PLURAL else "m")
            tokens.append(Token(swahili_adjective(entry("adj", predicate["adj"])["sw"], prefix), {"type": "adj", "concept": predicate["adj"], "role": "predicate"}))
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
    question_note = "Sumerian writing does not mark yes/no questions; the question mark is editorial."

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

    def verb(self, verb, person, tense, subject_noun=None, negative=False):
        v = form("verb", verb, "sux")
        if not v:
            return [gap("verb", verb)]
        if negative:
            template = self.IMPERFECTIVE[person] if tense == "present" else (self.PERFECTIVE_TRANS[person] if v.get("trans") else self.PERFECTIVE_INTRANS[person])
            # nu- negates the verbal chain: it replaces imperfective i3- and stands before mu-/ba-
            template = template.replace("i3-", "nu-", 1) if template.startswith("i3-") else "nu-" + template
            return self._verb_token(v, verb, person, tense, template, negative=True)
        if tense == "present":
            template = self.IMPERFECTIVE[person]
        else:
            template = self.PERFECTIVE_TRANS[person] if v.get("trans") else self.PERFECTIVE_INTRANS[person]
        return self._verb_token(v, verb, person, tense, template)

    def _verb_token(self, v, verb, person, tense, template, negative=False):
        if tense == "present":
            root, signs = v.get("maru", v["root"]), v.get("maru_signs", v["signs"])
        else:
            root, signs = v["root"], v["signs"]
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
        info = {"type": "verb", "verb": verb, "person": person, "tense": tense}
        conf = v.get("c", "medium")
        if negative:
            info["negative"] = True
            notes.append("The negative prefix nu- is written as in classical Sumerian; vowel contractions with the following prefix vary.")
            conf = "medium" if conf == "high" else conf
        return [self._token(pieces, info, conf, notes)]

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
        tokens += self.verb(verb, subject_person(subject), frame["tense"], negative=frame.get("negative", False))
        return tokens

    def identity(self, frame):
        if frame.get("negative"):
            self._refusal = "The negative copula of Archaic Sumerian is too poorly attested to compose; no form is given."
            return []
        subject = frame["subject"]
        tokens = self.np(subject, "subject") if subject.get("noun") else []
        pred = self.np(frame["predicate"], "predicate")
        if pred and not pred[-1].is_gap:
            last = pred[-1]
            person = subject_person(subject)
            pieces = last.flags["pieces"] + self._affix(self.COPULA[person].split("-"))
            pred[-1] = self._token(pieces, {**last.info, "copula": person, "role": "predicate"}, last.conf)
        return tokens + pred

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
    NOT_NOTE = "Archaic noenum (Ennius) is the older negative; non is used from Plautus on."

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
        gender = gender if gender in a else "m"
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
        gender = spec.get("agree", "m")
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
            info = {"type": "adj", "concept": spec["adj"], "case": case}
            if role == "predicate" and not spec.get("noun"):
                info["role"] = "predicate"
            tokens.append(Token(self._adj_case(a, gender, case), info, a.get("c", "high"), {"notes": notes}))
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

    def _ask(self, tokens: list[Token], frame: dict[str, Any]) -> list[Token]:
        """Yes/no question: the verb moves to the front and takes -ne (uiditne…?); nonne with a negative."""
        verb_index = next(i for i, t in enumerate(tokens) if t.info.get("type") in {"verb", "cop"})
        verb = tokens.pop(verb_index)
        if frame.get("negative"):
            tokens = [t for t in tokens if t.info.get("type") != "neg"]
            return [Token("nonne", {"type": "neg", "question": True}, "high", {"notes": [self.NOT_NOTE]}), verb] + tokens
        verb = Token(verb.text + "ne", {**verb.info, "question": True}, verb.conf, verb.flags)
        return [verb] + tokens

    def clause(self, frame):
        subject = frame["subject"]
        tokens: list[Token] = []
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        if frame.get("negative"):
            tokens.append(Token("non", {"type": "neg"}, "high", {"notes": [self.NOT_NOTE]}))
        tokens += self.verb(frame["verb"], subject_person(subject), frame["tense"])
        return self._ask(tokens, frame) if frame.get("question") else tokens

    def identity(self, frame):
        subject, predicate = frame["subject"], frame["predicate"]
        person = subject_person(subject)
        if not predicate.get("noun") and person in PLURAL:
            self._refusal = "Plural adjective forms are not in the ladder's Old Latin lexicon yet; no form is given."
            return []
        tokens = self.np(subject, "subject") if subject.get("noun") else []
        gender = noun_gender(subject.get("noun"), "la") if subject.get("noun") else ("f" if person in FEMININE else "m")
        tokens += self.np({**predicate, "agree": gender}, "predicate")
        if frame.get("negative"):
            tokens.append(Token("non", {"type": "neg"}, "high", {"notes": [self.NOT_NOTE]}))
        tokens.append(Token(self.COP[LATIN_PERSON_INDEX[person]], {"type": "cop", "person": person}, "medium", {"notes": ["ESOM is the archaic first-person form of later sum."]}))
        return self._ask(tokens, frame) if frame.get("question") else tokens

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
    LAYSA = {"1s": "lastu", "2ms": "lasta", "2fs": "lasti", "3ms": "laysa", "3fs": "laysat", "1p": "lasnā", "2p": "lastum", "3p": "laysū"}

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
        definite = spec.get("definite", True) and role not in {"predicate", "predicate_acc"}
        if role == "citation":
            definite = spec.get("definite", False)
        tokens: list[Token] = []
        gender = spec.get("agree", "m")
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
            tokens.append(Token(word, {"type": "noun", "concept": spec["noun"], "role": role, "case": case, "definite": definite}, n.get("c", "high"), {"fem_noun": n["f"].endswith("at")}))
        if spec.get("adj"):
            a = form("adj", spec["adj"], "ar")
            stem = a["f"] + ("at" if gender == "f" else "")
            word = self._noun_word(stem, case, definite, elided=bool(spec.get("noun")))
            info = {"type": "adj", "concept": spec["adj"], "case": case, "definite": definite}
            if role.startswith("predicate") and not spec.get("noun"):
                info["role"] = "predicate"
            tokens.append(Token(word, info, a.get("c", "high"), {"fem_noun": gender == "f"}))
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
        if frame.get("negative"):
            # mā + perfect 'did not', lā + imperfect 'does not'
            tokens.insert(0, Token("mā" if frame["tense"] == "past" else "lā", {"type": "neg"}))
        if subject.get("noun"):
            tokens += self.np({**subject, "definite": True}, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        return self._ask(tokens, frame)

    def _ask(self, tokens, frame):
        if not frame.get("question"):
            return tokens
        if tokens and tokens[0].info.get("type") == "neg":  # ʾa-lā / ʾa-mā: hal does not combine with a negative
            first = tokens[0]
            return [Token("ʾa-" + first.text, {"type": "neg", "question": True})] + tokens[1:]
        return [Token("hal", {"type": "q"})] + tokens

    def identity(self, frame):
        subject, predicate = frame["subject"], frame["predicate"]
        person = subject_person(subject)
        if not predicate.get("noun") and person in PLURAL:
            self._refusal = "Plural adjective forms are not in the ladder's Old Arabic lexicon yet; no form is given."
            return []
        gender = noun_gender(subject.get("noun"), "ar") if subject.get("noun") else ("f" if person in FEMININE else "m")
        tokens: list[Token] = []
        if frame.get("negative"):
            # laysa is conjugated and takes its predicate in the accusative: laysa l-maliku kabīran
            tokens.append(Token(self.LAYSA[person], {"type": "cop", "person": person, "negative": True}, "high", {"plural_verb": person == "3p"}))
        elif not subject.get("noun"):
            tokens.append(Token(self.PRON[person], {"type": "pron", "person": person}))
        if subject.get("noun"):
            tokens += self.np({**subject, "definite": True}, "subject")
        tokens += self.np({**predicate, "definite": False, "agree": gender}, "predicate_acc" if frame.get("negative") else "predicate")
        return self._ask(tokens, frame)

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
    question_note = "Ge'ez marks the questioned word with the enclitic -nu."

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
            info = {"type": "adj", "concept": spec["adj"]}
            if role == "predicate" and not spec.get("noun"):
                info["role"] = "predicate"
            tokens.append(Token(a["f"] + ("a" if accusative else ""), info, a.get("c", "high")))
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
        verb = tokens[0]
        if not verb.is_gap and (frame.get("negative") or frame.get("question")):
            # ʾi- negates the verb (ʾigabra 'he did not make'); -nu marks the question (gabranu?)
            text = ("ʾi" if frame.get("negative") else "") + verb.text + ("nu" if frame.get("question") else "")
            info = {**verb.info, **({"negative": True} if frame.get("negative") else {}), **({"question": True} if frame.get("question") else {})}
            tokens[0] = Token(text, info, verb.conf, verb.flags)
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        return tokens

    def identity(self, frame):
        subject, predicate = frame["subject"], frame["predicate"]
        person = subject_person(subject)
        if frame.get("negative"):
            self._refusal = "Negated nominal sentences are not modelled for Ge'ez yet; no form is given."
            return []
        gender = noun_gender(subject.get("noun"), "gez") if subject.get("noun") else ("f" if person in FEMININE else "m")
        if not predicate.get("noun") and (person in PLURAL or gender == "f"):
            self._refusal = "Feminine and plural adjective forms are not in the ladder's Ge'ez lexicon yet; no form is given."
            return []
        if subject.get("noun"):
            # nəguś ʿabiy wəʾətu 'the king is great': the 3rd-person pronoun serves as copula
            cop = "yəʾəti" if gender == "f" else "wəʾətu"
            tokens = self.np(subject, "subject") + self.np(predicate, "predicate") + [Token(cop, {"type": "cop", "person": "3fs" if gender == "f" else "3ms"}, "medium")]
        else:
            tokens = [Token(self.PRON[person], {"type": "pron", "person": person})] + self.np(predicate, "predicate")
        if frame.get("question") and tokens:
            first = tokens[0]
            tokens[0] = Token(first.text + "nu", {**first.info, "question": True}, first.conf, first.flags)
        return tokens

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
    NEG_COP = {"1s": "ʾaydällähum", "2ms": "ʾaydällähəm", "2fs": "ʾaydälläšəm", "3ms": "ʾaydälläm", "3fs": "ʾaydälläččəm",
               "1p": "ʾaydällänəm", "2p": "ʾaydällaččəhum", "3p": "ʾaydällum"}
    NEG_IMPF = {"1s": ("ʾal", ""), "2ms": ("ʾat", ""), "2fs": ("ʾat", "i"), "3ms": ("ʾay", ""), "3fs": ("ʾat", ""),
                "1p": ("ʾan", ""), "2p": ("ʾat", "u"), "3p": ("ʾay", "u")}
    question_note = "Amharic marks a yes/no question by intonation only (written with ፧ or ?)."
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
        if role == "predicate" and not noun:
            words = [(w, {**i, "role": "predicate"}, c) for w, i, c in words]
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

    @staticmethod
    def _m(word: str) -> str:
        return word + ("m" if word[-1] in "aäeiouə" else "əm")

    def _negative(self, v: dict, verb: str, person: str, tense: str) -> list[Token]:
        info = {"type": "verb", "verb": verb, "person": person, "tense": tense, "negative": True}
        if tense == "past":
            perf = v["perf"][PERSONS.index(person)]
            word = self._m("ʾal" + (perf[1:] if perf.startswith("ʾ") else perf))  # ʾalsärram 'he did not make'
            return [Token(word, info, "medium", {"notes": ["Negative perfect: ʾal- … -m."]})]
        prefix, suffix = self.NEG_IMPF[person]
        stem = v["impf"][1:] if v["impf"].startswith("ʾ") else v["impf"]
        if suffix and stem[-1] in "aä":
            stem = stem[:-1]
        word = self._m(prefix + stem + suffix)  # ʾaysäram 'he does not make'
        return [Token(word, info, "medium", {"notes": ["Negative imperfect: ʾay-/ʾat-/ʾal- … -m."]})]

    def verb(self, verb, person, tense, subject_noun=None, negative=False):
        v = form("verb", verb, "am")
        if not v:
            return [gap("verb", verb)]
        if negative:
            return self._negative(v, verb, person, tense)
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
        tokens += self.verb(frame["verb"], person, frame["tense"], negative=frame.get("negative", False))
        return tokens

    def identity(self, frame):
        subject = frame["subject"]
        person = subject_person(subject)
        if subject.get("noun"):
            n = form("noun", subject["noun"], "am")
            person = "3fs" if n and n["g"] == "f" else "3ms"
            tokens = self.np({**subject, "definite": True}, "subject")
        else:
            tokens = [Token(self.PRON[person], {"type": "pron", "person": person})]
        cop = (Token(self.NEG_COP[person], {"type": "cop", "person": person, "negative": True}, "medium")
               if frame.get("negative") else Token(self.COP[person], {"type": "cop", "person": person}))
        return tokens + self.np(frame["predicate"], "predicate") + [cop]

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
    question_note = "No yes/no question particle can be reconstructed for Proto-Semitic; the question mark is editorial."

    def np(self, spec, role, verb=None):
        case = {"subject": "nom", "predicate": "nom", "citation": "nom"}.get(role, "acc")
        prep = (form("verb", verb, "sem") or {}).get("prep") if role == "object" and verb else None
        if prep:
            case = "gen"
        tokens: list[Token] = []
        gender = spec.get("agree", "m")
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
            info = {"type": "adj", "concept": spec["adj"]}
            if role == "predicate" and not spec.get("noun"):
                info["role"] = "predicate"
            tokens.append(Token(a["f"] + ("at" if gender == "f" else "") + self.CASE_END[case], info, a.get("c", "medium")))
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
        if frame.get("negative"):
            tokens.insert(0, Token("lā", {"type": "neg"}, "medium", {"notes": ["*lā is the reconstructed verbal negative (Arabic lā, Hebrew lōʾ, Akkadian lā)."]}))
        if subject.get("noun"):
            tokens += self.np(subject, "subject")
        if frame.get("object"):
            tokens += self.np(frame["object"], "object", frame["verb"])
        return tokens

    def identity(self, frame):
        subject, predicate = frame["subject"], frame["predicate"]
        person = subject_person(subject)
        if frame.get("negative"):
            self._refusal = "The negation of Proto-Semitic nominal sentences cannot be reconstructed securely; no form is given."
            return []
        if not predicate.get("noun") and person in PLURAL:
            self._refusal = "Plural adjective forms are not reconstructed in the ladder yet; no form is given."
            return []
        gender = noun_gender(subject.get("noun"), "sem") if subject.get("noun") else ("f" if person in FEMININE else "m")
        if subject.get("noun"):
            tokens = self.np(subject, "subject")
            if tokens and tokens[0].is_gap:
                return tokens
        else:
            tokens = [Token(self.PRON[person], {"type": "pron", "person": person}, "medium")]
        return tokens + self.np({**predicate, "agree": gender}, "predicate")

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
    DEPENDENT = {"1s": "wj", "2ms": "tw", "2fs": "tn", "3ms": "sw", "3fs": "sj", "1p": "n", "2p": "ṯn", "3p": "sn"}
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
            info = {"type": "adj", "concept": spec["adj"]}
            if role == "predicate" and not spec.get("noun"):
                info["role"] = "predicate"
            tokens.append(Token(word, info, a.get("c", "high"), {"glyphs": glyphs}))
        return tokens

    def _suffix_glyphs(self, suffix: str) -> str:
        return scripts.hieroglyphs(scripts.EGYPTIAN_SUFFIX_GLYPHS[suffix])

    def verb(self, verb, person, tense, subject_noun=None, negative=False):
        v = form("verb", verb, "egy")
        if not v:
            return [gap("verb", verb)]
        # Gardiner §105: n sḏm.f 'he did not hear', but n sḏm.n.f 'he does not (cannot) hear'
        with_n = (tense == "present") if negative else (tense == "past")
        stem = self._form(v["perf"] if (tense == "past" or negative) else v["pres"])
        glyphs = self._glyphs(stem, v.get("gl"))
        parts = [stem]
        if with_n:
            parts.append("n")
            glyphs += scripts.hieroglyphs(scripts.EGYPTIAN_PERFECT_N)
        if not subject_noun:
            suffix = self.SUFFIX[person]
            parts.append(suffix)
            glyphs += self._suffix_glyphs(suffix)
        notes = [v["note"]] if v.get("note") else []
        if negative:
            notes.append("n sḏm.f 'did not' (past)" if tense == "past" else "n sḏm.n.f 'does not, cannot' (present)")
        else:
            notes.append("sḏm.n.f perfect" if tense == "past" else "sḏm.f (circumstantial/present)")
        info = {"type": "verb", "verb": verb, "person": person, "tense": tense}
        if negative:
            info["negative"] = True
        if subject_noun:
            info["noun_subject"] = True
        return [Token(".".join(parts), info, v.get("c", "high"), {"glyphs": glyphs, "notes": notes})]

    def citation_verb(self, verb):
        v = form("verb", verb, "egy")
        if not v:
            return [gap("verb", verb)]
        stem = self._form(v["perf"])
        return [Token(stem, {"type": "verb", "verb": verb}, v.get("c", "high"), {"glyphs": self._glyphs(stem, v.get("gl"))})]

    def _particles(self, frame) -> list[Token]:
        tokens: list[Token] = []
        if frame.get("question"):
            tokens.append(Token("jn", {"type": "q"}, "high", {"glyphs": scripts.hieroglyphs(["M017", "N035"]), "notes": ["jn introduces a yes/no question."]}))
        if frame.get("negative"):
            tokens.append(Token("n", {"type": "neg"}, "high", {"glyphs": scripts.hieroglyph("D035")}))
        return tokens

    def clause(self, frame):
        subject, verb = frame["subject"], frame["verb"]
        person = subject_person(subject)
        v = form("verb", verb, "egy") or {}
        tokens = self._particles(frame) + self.verb(verb, person, frame["tense"], subject if subject.get("noun") else None, frame.get("negative", False))
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
        subject, predicate = frame["subject"], frame["predicate"]
        person = subject_person(subject)
        if frame.get("negative"):
            self._refusal = "Negated nominal sentences (n … js) are not modelled for Egyptian yet; no form is given."
            return []
        question = self._particles(frame)
        if not predicate.get("noun"):
            # adjectival sentence: the adjective comes first and does not agree (nfr sw 'he is good', ꜥꜣ nswt 'the king is great')
            adj = self.np({"noun": None, "adj": predicate["adj"]}, "predicate")
            if subject.get("noun"):
                return question + adj + self.np(subject, "subject")
            dep = self.DEPENDENT[person]
            return question + adj + [Token(dep, {"type": "pron", "person": person}, "high", {"glyphs": self._glyphs(dep, None)})]
        if subject.get("noun"):
            # A pw B: bꜣk pw nswt 'the king is a servant' (Gardiner §130)
            pw = Token("pw", {"type": "cop", "person": "3ms", "pw": True}, "medium", {"glyphs": scripts.hieroglyphs(["Q003", "G043"]), "notes": ["Nominal sentence of the type A pw B."]})
            return question + self.np(predicate, "predicate") + [pw] + self.np(subject, "subject")
        pron = self.PRON[person]
        return question + [Token(pron, {"type": "pron", "person": person}, "high", {"glyphs": self._glyphs(pron, None)})] + self.np(predicate, "predicate")

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
        self._refusal = ("Archaic hieroglyphic writing does not record full verbal sentences, negation or questions; only a "
                         "logographic label of the content words is given.")
        tokens: list[Token] = []
        if frame["subject"].get("noun"):
            tokens += Egyptian.np(self, frame["subject"], "subject")
        if frame.get("object"):
            tokens += Egyptian.np(self, frame["object"], "label")
        if not tokens:
            tokens.append(Token("", {"type": "none"}))
        return [t for t in tokens if t.text]

    def identity(self, frame):
        self._refusal = "Nominal sentences are not attested this early; the label shows the content words alone, as on Early Dynastic seals."
        tokens = Egyptian.np(self, frame["subject"], "label") if frame["subject"].get("noun") else []
        return tokens + Egyptian.np(self, frame["predicate"], "label")

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
        self._refusal = "No Proto-World grammar has been proposed; only the noun roots are listed."
        nouns = [n for n in (frame["subject"].get("noun"), frame["predicate"].get("noun")) if n]
        return [t for t in (self._root(n) for n in nouns) if not t.is_gap]


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
