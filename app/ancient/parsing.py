"""Parsers that turn text in any ladder language into a language-neutral frame.

English and Swahili have rule-based parsers. Every ancient language is parsed
by matching input against an index of all forms its realizer can produce,
in transliteration and in native script, so whatever the ladder writes it can
also read back.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

from .grammar import PERSONS, REALIZERS, loose_key
from .lexicon import adjectives, english_index, nouns, swahili_adjective, verbs

Frame = dict[str, Any]


class ParseResult(dict):
    """frame + diagnostics: unknown words, ambiguities and parser notes."""


def _result(frame: Frame | None, unknown: list[str], notes: list[str], ambiguities: list[str] | None = None,
            dropped: list[str] | None = None) -> ParseResult:
    return ParseResult(frame=frame, unknown=unknown, notes=notes, ambiguities=ambiguities or [], dropped=dropped or [])


def _flag(frame: Frame | None, negative: bool = False, question: bool = False) -> Frame | None:
    if frame and frame.get("kind") in {"clause", "identity"}:
        if negative:
            frame["negative"] = True
        if question:
            frame["question"] = True
    return frame


# ======================================================================= English
FEMALE_NOUNS = {"woman", "mother"}
EN_PRONOUNS = {"i": "1s", "you": "2ms", "he": "3ms", "she": "3fs", "we": "1p", "they": "3p"}
EN_COPULA = {"am", "is", "are", "was", "were"}
EN_DO = {"do", "does", "did"}
EN_PERFECT = {"have", "has", "had"}
EN_MODAL = {"will", "shall"}
EN_NEG = {"not", "never"}
EN_ARTICLES = {"the", "a", "an"}
EN_PREPS = {"in", "to", "into", "at", "toward", "towards", "on", "upon"}
# Words that carry no content of their own; anything else left over is reported, never silently dropped.
EN_FUNCTION = EN_ARTICLES | EN_PREPS | {"it", "him", "her", "them", "my", "our", "your", "his", "their", "its", "very", "really", "just", "please"}
EN_CONTRACTIONS = {"i'm": "i am", "i've": "i have", "you're": "you are", "we're": "we are", "they're": "they are",
                   "he's": "he is", "she's": "she is", "we've": "we have", "they've": "they have", "you've": "you have",
                   "don't": "do not", "doesn't": "does not", "didn't": "did not", "isn't": "is not", "aren't": "are not",
                   "wasn't": "was not", "weren't": "were not", "haven't": "have not", "hasn't": "has not", "hadn't": "had not",
                   "won't": "will not", "shan't": "shall not"}
TRUST_IDIOM = re.compile(r"\b(have|has|had)?\s*(put|placed|place|puts|places|putting|placing)\s+(?:my|our|your|his|her|their|all\s+my)\s+trust\s+in\b")


def _english_np(words: list[str], i: int, unknown: list[str]) -> tuple[dict[str, Any] | None, int]:
    definite = True
    if i < len(words) and words[i] in EN_ARTICLES:
        definite = words[i] == "the"
        i += 1
    adj = None
    while i < len(words):
        hits = english_index().get(words[i], [])
        adj_hit = next((h for h in hits if h[0] == "adj"), None)
        noun_hit = next((h for h in hits if h[0] == "noun"), None)
        if adj_hit and not noun_hit:
            adj = adj_hit[1]
            i += 1
            continue
        if noun_hit:
            np = {"noun": noun_hit[1], "adj": adj, "definite": definite}
            if noun_hit[2].get("plural"):
                np["plural"] = words[i]
            return np, i + 1
        break
    if i < len(words) and words[i] not in EN_PREPS and not english_index().get(words[i]) and words[i] not in EN_NEG:
        unknown.append(words[i])
        return None, i + 1
    if adj:
        return {"noun": None, "adj": adj, "definite": definite}, i
    return None, i


def _leftover(words: list[str]) -> list[str]:
    """Content words left over after the parse: these are reported as not translated."""
    return [w for w in words if w not in EN_FUNCTION]


def parse_english(text: str) -> ParseResult:
    notes: list[str] = []
    unknown: list[str] = []
    dropped: list[str] = []
    raw = unicodedata.normalize("NFC", text.strip().lower()).replace("’", "'")
    question = raw.endswith("?")
    t = raw
    for short, full in EN_CONTRACTIONS.items():
        t = re.sub(rf"\b{re.escape(short)}", full, t)
    idiom = TRUST_IDIOM.search(t)
    if idiom:
        past = bool(idiom.group(1)) or idiom.group(2) in {"put", "placed"}
        t = t[: idiom.start()] + ("trusted in" if past else "trust in") + t[idiom.end():]
        notes.append("Read the idiom 'put my trust in' as the verb 'trust'.")
    topic = None
    if "," in t:
        left, right = t.split(",", 1)
        left_words = re.findall(r"[a-z]+", left)
        np, end = _english_np(left_words, 0, [])
        if np and np.get("noun") and end == len(left_words):
            topic, t = np, right
            notes.append("Fronted topic detected; it is treated as the object and realized in each language's normal word order.")
    words = [w for w in re.findall(r"[a-z]+", t) if w not in {"it", "him", "her", "them"}]
    if not words:
        return _result(None, unknown, notes)

    # single word / citation forms
    if len(words) == 1 or (len(words) == 2 and words[0] == "to"):
        word = words[-1]
        hits = english_index().get(word, [])
        if hits:
            kind, concept, _features = next((h for h in hits if h[0] == ("verb" if words[0] == "to" else h[0])), hits[0])
            return _result({"kind": "word", "word_kind": kind, "concept": concept}, unknown, notes)
        return _result(None, [word], notes)

    negative = False
    lead = None
    if words[0] in EN_COPULA | EN_DO | EN_PERFECT | EN_MODAL and len(words) > 2:
        lead = words[0]  # inverted question: "Did the king…", "Is the sun…"
        question = True
        words = words[1:]

    def plural_note(np: dict[str, Any]) -> None:
        if np and np.get("plural"):
            dropped.append(f"plural '{np['plural']}' (translated as singular)")
            notes.append("The ladder has singular noun forms only; plural nouns are translated as singular.")

    i = 0
    subject: dict[str, Any] | None = None
    if words[0] in EN_PRONOUNS:
        subject = {"person": EN_PRONOUNS[words[0]]}
        if words[0] == "you":
            notes.append("English 'you' does not mark gender or number; masculine singular was used where a language requires a choice.")
        i = 1
    else:
        np, j = _english_np(words, 0, unknown)
        if np and np.get("noun") and j < len(words):
            plural_note(np)
            subject, i = {"person": "3ms", "noun": np["noun"], "adj": np.get("adj")}, j
        elif np and j >= len(words) and not lead:
            plural_note(np)
            np.pop("plural", None)
            return _result({"kind": "np", "np": np}, unknown, notes, dropped=dropped)
    if subject and subject.get("noun"):
        subject["person"] = "3fs" if subject["noun"] in FEMALE_NOUNS else "3ms"

    def take_negation() -> None:
        nonlocal i, negative
        while i < len(words) and words[i] in EN_NEG:
            if words[i] == "never":
                notes.append("'never' is translated as a plain negative.")
            negative = True
            i += 1

    tense = "present"
    copular = False
    aux = lead
    if aux is None and i < len(words) and words[i] in EN_COPULA | EN_DO | EN_PERFECT | EN_MODAL:
        aux = words[i]
        i += 1
    take_negation()
    if aux in EN_COPULA:
        tense = "past" if aux in {"was", "were"} else "present"
        nxt = words[i] if i < len(words) else ""
        copular = not any(h[0] == "verb" for h in english_index().get(nxt, []))
    elif aux in {"did", "have", "has", "had"}:
        tense = "past"
    elif aux in EN_MODAL:
        notes.append("Future tense is not modelled; the present/imperfective is used.")

    if copular and subject:
        np, j = _english_np(words, i, unknown)
        if np:
            plural_note(np)
            dropped += [f"'{w}'" for w in _leftover(words[j:])]
            if tense == "past":
                notes.append("Past 'was/were' is translated with the timeless nominal sentence.")
            predicate = {"noun": np["noun"], "adj": np.get("adj")}
            frame = {"kind": "identity", "subject": subject, "predicate": predicate}
            return _result(_flag(frame, negative, question), unknown, notes, dropped=dropped)
        return _result(None, unknown, notes, dropped=dropped)

    verb = None
    while i < len(words):
        if words[i] in EN_NEG:
            take_negation()
            continue
        hit = next((h for h in english_index().get(words[i], []) if h[0] == "verb"), None)
        if hit:
            verb = hit[1]
            if hit[2].get("tense") == "past":
                tense = "past"
            i += 1
            break
        unknown.append(words[i])
        i += 1
    if not verb:
        return _result(None, unknown, notes, dropped=dropped)
    if subject is None:
        subject = {"person": "3ms"}
    while i < len(words) and words[i] in EN_PREPS:
        i += 1
    obj = None
    if i < len(words):
        obj, i = _english_np(words, i, unknown)
        if obj:
            plural_note(obj)
            obj.pop("plural", None)
    rest = words[i:]
    if rest:
        phrase = " ".join(rest)
        if _leftover(rest):
            dropped.append(f"'{phrase}'")
    if topic and not obj:
        obj = topic
    frame = {"kind": "clause", "subject": subject, "verb": verb, "tense": tense, "object": obj}
    return _result(_flag(frame, negative, question), unknown, notes, dropped=dropped)


# ======================================================================= Swahili
SW_PRONOUNS = {"mimi": "1s", "wewe": "2ms", "yeye": "3ms", "sisi": "1p", "ninyi": "2p", "nyinyi": "2p", "wao": "3p"}
SW_SUBJECT = {"ni": "1s", "u": "2ms", "a": "3ms", "tu": "1p", "m": "2p", "wa": "3p"}
SW_TENSE = {"li": "past", "me": "past", "na": "present", "ta": "present"}
SW_VERB = re.compile(r"^(ni|u|a|tu|mu|m|wa|i|li|ki|vi|zi|ya|ku|pa)(li|na|me|ta)(ku|kw)?([a-z]+)$")


@lru_cache(maxsize=1)
def _sw_maps() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    noun_map = {item["sw"]["f"].lower(): concept for concept, item in nouns().items()}
    verb_map: dict[str, str] = {}
    for concept, item in verbs().items():
        verb_map.setdefault(item["sw"]["root"], concept)
    adj_map: dict[str, str] = {}
    for concept, item in adjectives().items():
        for prefix in ("n", "m", "ma", "ki", "vi", "", "wa", "mi"):
            adj_map[swahili_adjective(item["sw"], prefix)] = concept
    return noun_map, verb_map, adj_map


SW_NEG_PREFIXES = {"si": "1s", "hu": "2ms", "ha": "3ms", "hatu": "1p", "ham": "2p", "hamu": "2p", "hawa": "3p",
                   "hau": "3ms", "hai": "3ms", "hali": "3ms", "haki": "3ms", "havi": "3ms", "hazi": "3ms", "haya": "3ms"}


def _sw_negative(word: str, verb_map: dict[str, str]) -> tuple[str, str, str] | None:
    """Negative verb forms: hakuona 'did not see', haoni 'does not see', sikula 'I did not eat'."""
    for prefix in sorted(SW_NEG_PREFIXES, key=len, reverse=True):
        if not word.startswith(prefix):
            continue
        rest = word[len(prefix):]
        if rest.startswith(("ku", "kw")) and rest[2:] in verb_map:  # hakuona, hakula, hakwenda
            return verb_map[rest[2:]], "past", SW_NEG_PREFIXES[prefix]
        for candidate in (rest, rest[:-1] + "a" if rest.endswith("i") else ""):
            if candidate in verb_map:
                return verb_map[candidate], "present", SW_NEG_PREFIXES[prefix]
    return None


def _sw_np(words: list[str], noun_map: dict[str, str], adj_map: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
    np: dict[str, Any] | None = None
    rest: list[str] = []
    for w in words:
        if np is None and w in noun_map:
            np = {"noun": noun_map[w], "adj": None, "definite": True}
        elif np is not None and w in adj_map and np["adj"] is None:
            np["adj"] = adj_map[w]
        elif np is None and w in adj_map:
            np = {"noun": None, "adj": adj_map[w], "definite": True}
        else:
            rest.append(w)
    return np, rest


def parse_swahili(text: str) -> ParseResult:
    notes: list[str] = []
    unknown: list[str] = []
    raw = unicodedata.normalize("NFC", text.strip().lower())
    question = raw.endswith("?")
    words = re.findall(r"[a-z']+", raw)
    if words and words[0] == "je":
        question = True
        words = words[1:]
    noun_map, verb_map, adj_map = _sw_maps()
    if not words:
        return _result(None, unknown, notes)
    if len(words) == 1:
        w = words[0]
        if w in noun_map:
            return _result({"kind": "word", "word_kind": "noun", "concept": noun_map[w]}, unknown, notes)
        if w.startswith("ku") and w[2:] in verb_map:
            return _result({"kind": "word", "word_kind": "verb", "concept": verb_map[w[2:]]}, unknown, notes)
        if w in adj_map or w.lstrip("-") in adj_map:
            return _result({"kind": "word", "word_kind": "adj", "concept": adj_map.get(w) or adj_map[w.lstrip("-")]}, unknown, notes)

    # Nominal sentence: SUBJECT ni/si PREDICATE (Mfalme ni mkubwa, Mimi si mtumishi)
    cop_at = next((k for k, w in enumerate(words) if w in {"ni", "si"}), None)
    if cop_at is not None and cop_at > 0:
        before, after = words[:cop_at], words[cop_at + 1:]
        subject: dict[str, Any] | None = None
        if len(before) == 1 and before[0] in SW_PRONOUNS:
            subject = {"person": SW_PRONOUNS[before[0]]}
        else:
            np, rest = _sw_np(before, noun_map, adj_map)
            if np and np.get("noun"):
                subject = {"person": "3fs" if np["noun"] in FEMALE_NOUNS else "3ms", "noun": np["noun"], "adj": np["adj"]}
                unknown += rest
        predicate, rest = _sw_np(after, noun_map, adj_map)
        if subject and predicate:
            unknown += rest
            frame = {"kind": "identity", "subject": subject, "predicate": {"noun": predicate["noun"], "adj": predicate["adj"]}}
            return _result(_flag(frame, words[cop_at] == "si", question), unknown, notes)

    subject = None
    verb = tense = None
    negative = False
    obj: dict[str, Any] | None = None
    pending_noun: dict[str, Any] | None = None
    for w in words:
        if w in SW_PRONOUNS and subject is None:
            subject = {"person": SW_PRONOUNS[w]}
            continue
        noun_key = w if w in noun_map else (w[:-2] if w.endswith("ni") and w[:-2] in noun_map else None)
        if noun_key:
            np = {"noun": noun_map[noun_key], "adj": None, "definite": True}
            if verb is None:
                pending_noun = np
            else:
                obj = np
            continue
        if w in adj_map:
            target = obj if obj is not None else pending_noun
            if target is not None:
                target["adj"] = adj_map[w]
            continue
        found = None
        m = SW_VERB.match(w)
        if m and verb is None:
            root = m.group(4)
            if root not in verb_map and m.group(3):
                root = m.group(3) + root
            if root in verb_map:
                found = (verb_map[root], SW_TENSE[m.group(2)], SW_SUBJECT.get(m.group(1), "3ms"))
                if m.group(2) == "ta":
                    notes.append("Swahili future -ta- is mapped to the present/imperfective.")
        if found is None and verb is None:
            neg = _sw_negative(w, verb_map)
            if neg:
                found, negative = neg, True
        if found:
            verb, tense, person = found
            if pending_noun is not None:
                subject = {"person": "3fs" if pending_noun["noun"] in FEMALE_NOUNS else "3ms", "noun": pending_noun["noun"], "adj": pending_noun.get("adj")}
                pending_noun = None
            elif subject is None:
                subject = {"person": person}
            continue
        unknown.append(w)
    if verb:
        if subject and subject.get("person") == "3ms" and not subject.get("noun"):
            notes.append("Swahili a- does not mark gender; masculine was used where a language requires a choice.")
        frame = {"kind": "clause", "subject": subject or {"person": "3ms"}, "verb": verb, "tense": tense, "object": obj}
        return _result(_flag(frame, negative, question), unknown, notes)
    if pending_noun:
        return _result({"kind": "np", "np": pending_noun}, unknown, notes)
    return _result(None, unknown, notes)


# ============================================================ ancient languages
def _exact_key(text: str) -> str:
    text = re.sub(r"[*።]", "", unicodedata.normalize("NFC", text.lower()))
    return re.sub(r"[\s፡·,]+", " ", text).strip()


def _person_for(noun: str) -> str:
    return "3fs" if noun in FEMALE_NOUNS else "3ms"


FLAGS = ({}, {"negative": True}, {"question": True}, {"negative": True, "question": True})


def _synthetic_frames(lang: str) -> list[Frame]:
    frames: list[Frame] = []
    noun_ids = list(nouns())
    verb_ids = list(verbs())
    adj_ids = list(adjectives())
    for verb in verb_ids:
        for person in PERSONS:
            for tense in ("past", "present"):
                for flags in FLAGS:
                    frames.append({"kind": "clause", "subject": {"person": person}, "verb": verb, "tense": tense, "object": None, **flags})
    for noun in noun_ids:
        frames.append({"kind": "word", "word_kind": "noun", "concept": noun})
        for adj in (None, *adj_ids):
            for definite in (True, False):
                frames.append({"kind": "np", "np": {"noun": noun, "adj": adj, "definite": definite}})
            for verb in verb_ids:
                for definite in (True, False):  # Old Arabic marks (in)definiteness on objects: baytan / al-bayta
                    frames.append({"kind": "clause", "subject": {"person": "1s"}, "verb": verb, "tense": "past",
                                   "object": {"noun": noun, "adj": adj, "definite": definite}})
            for verb in ("make", "go"):
                for tense in ("past", "present"):
                    for flags in FLAGS[:2]:
                        frames.append({"kind": "clause", "subject": {"person": _person_for(noun), "noun": noun, "adj": adj}, "verb": verb, "tense": tense, "object": None, **flags})
        for person in PERSONS:
            for flags in FLAGS:
                frames.append({"kind": "identity", "subject": {"person": person}, "predicate": {"noun": noun, "adj": None}, **flags})
        for adj in adj_ids:
            frames.append({"kind": "identity", "subject": {"person": "1s"}, "predicate": {"noun": noun, "adj": adj}})
            for flags in FLAGS:
                frames.append({"kind": "identity", "subject": {"person": _person_for(noun), "noun": noun}, "predicate": {"noun": None, "adj": adj}, **flags})
        for flags in FLAGS:
            frames.append({"kind": "identity", "subject": {"person": _person_for(noun), "noun": noun}, "predicate": {"noun": "servant", "adj": None}, **flags})
            frames.append({"kind": "identity", "subject": {"person": "3ms", "noun": "king"}, "predicate": {"noun": noun, "adj": None}, **flags})
    for verb in verb_ids:
        for tense in ("past", "present"):
            for noun in ("king", "woman", "sun", "sky", "water", "river"):
                for flags in FLAGS:
                    frames.append({"kind": "clause", "subject": {"person": _person_for(noun), "noun": noun, "adj": None}, "verb": verb, "tense": tense, "object": None, **flags})
    for adj in adj_ids:
        frames.append({"kind": "word", "word_kind": "adj", "concept": adj})
        for person in PERSONS:
            frames.append({"kind": "identity", "subject": {"person": person}, "predicate": {"noun": "king", "adj": adj}})
            for flags in FLAGS:
                frames.append({"kind": "identity", "subject": {"person": person}, "predicate": {"noun": None, "adj": adj}, **flags})
    for verb in verb_ids:
        frames.append({"kind": "word", "word_kind": "verb", "concept": verb})
    return frames


@lru_cache(maxsize=None)
def form_index(lang: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    """(exact, loose) indexes: every surface form the realizer can write -> token infos.

    Exact keys cover transliteration and native scripts; loose keys ignore
    diacritics, sign indices and separators. Exact matches always win so that,
    for example, Egyptian preposition r is never confused with rꜥ 'sun'.
    """
    realizer = REALIZERS[lang]
    exact: dict[str, list[dict[str, Any]]] = {}
    loose: dict[str, list[dict[str, Any]]] = {}

    def put(index: dict[str, list[dict[str, Any]]], key: str, info: dict[str, Any]) -> None:
        if not key:
            return
        bucket = index.setdefault(key, [])
        if info not in bucket:
            bucket.append(info)

    for frame in _synthetic_frames(lang):
        try:
            realizer._refusal = None
            tokens = realizer.tokens_for(frame)
        except (KeyError, TypeError):
            continue
        for token in tokens:
            if token.is_gap or not token.text:
                continue
            info = dict(token.info)
            put(exact, _exact_key(token.text), info)
            put(loose, loose_key(token.text), info)
            try:
                for rendering in realizer.render_scripts([token]).values():
                    put(exact, _exact_key(rendering), info)
            except (KeyError, ValueError):
                pass
    return exact, loose


def _split_words(text: str) -> list[str]:
    return [w for w in re.split(r"[\s፡።·,;]+", unicodedata.normalize("NFC", text.strip())) if w]


QUESTION_MARKS = "?፧؟"


def _akkadian_syllabic(word: str) -> str:
    """Join a sign-by-sign transliteration into the word: ša-ar-ru-um -> šarrum, a-wi-lu-um -> awilum."""
    if "-" not in word:
        return word
    parts = [re.sub(r"[\d₀-₉]", "", p) for p in word.split("-") if p]
    out = parts[0] if parts else ""
    for part in parts[1:]:
        if out and part and out[-1] in "aeiuāēīūâêîû" and loose_key(out[-1]) == loose_key(part[0]) and len(part) > 1:
            out += part[1:]  # CV-VC spelling of one closed syllable
        else:
            out += part
    return out


def parse_ancient(text: str, lang: str) -> ParseResult:
    exact, loose = form_index(lang)
    stripped = text.strip()
    question = stripped.endswith(tuple(QUESTION_MARKS))
    words = _split_words(stripped.rstrip(QUESTION_MARKS + " ።"))
    joined = [_akkadian_syllabic(w) for w in words] if lang == "old_akkadian" else words
    matches: list[tuple[str, list[dict[str, Any]]]] = []
    unknown: list[str] = []
    i = 0
    while i < len(words):
        found = None
        for source in ((words, joined) if joined is not words else (words,)):
            for index, keyer in ((exact, _exact_key), (loose, loose_key)):
                for n in (3, 2, 1):
                    if i + n > len(words):
                        continue
                    phrase = " ".join(source[i:i + n])
                    key = keyer(phrase)
                    if key in index:
                        found = (n, phrase, index[key])
                        break
                if found:
                    break
            if found:
                break
        if found:
            n, phrase, infos = found
            matches.append((phrase, infos))
            i += n
        else:
            unknown.append(words[i])
            i += 1
    result = _assemble(matches, unknown, lang, question)
    if lang == "old_arabic" and re.search(r"[\U00010A80-\U00010A9F\u0600-\u06FF]", text):
        result["ambiguities"].append(
            "Safaitic and early Arabic script write no short vowels (and early Arabic no dots), so person, "
            "tense and even some words can be read several ways; the first matching reading was used.")
    return result


def _best_concept(entry: dict[str, Any], roles: tuple[str, ...], verb: str | None, lang: str) -> str:
    """Among homographs, keep the noun whose regular form in this role reproduces the written word."""
    if len(entry["concepts"]) < 2:
        return entry["concept"]
    realizer = REALIZERS[lang]
    target = _exact_key(entry["phrase"])
    for concept in entry["concepts"]:
        for role in roles:
            try:
                tokens = realizer.np({"noun": concept, "adj": None, "definite": True}, role, verb)
            except (KeyError, TypeError):
                continue
            if any(_exact_key(t.text) == target for t in tokens):
                return concept
    return entry["concepts"][0]


EGYPTIAN = {"old_egyptian", "middle_egyptian", "archaic_hieroglyphic"}
THIRD_PERSON = {"3ms", "3fs"}


def _assemble(matches: list[tuple[str, list[dict[str, Any]]]], unknown: list[str], lang: str, question: bool = False) -> ParseResult:
    notes: list[str] = []
    ambiguities: list[str] = []
    verb_phrase = None
    verb_cands: list[dict[str, Any]] = []
    nouns_seen: list[dict[str, Any]] = []
    copula_person = None
    cop_negative = False
    pron_person = None
    pending_adj = None
    predicate_adj = None
    leading_adj = False
    pw_at = None
    copula_alt = None
    citation_verbs: list[str] = []
    negative = False
    content_seen = False
    for phrase, infos in matches:
        types = {i["type"] for i in infos}
        if any(i.get("question") for i in infos) or "q" in types:
            question = True
        if types == {"q"}:
            continue
        # A negative particle (non, mā, lā, *lā, Egyptian n) – Egyptian n is also a pronoun and a preposition,
        # so a mixed reading counts as negation only before the verb or predicate.
        if "neg" in types and (types == {"neg"} or not content_seen):
            negative = True
            continue
        conjugated = [i for i in infos if i["type"] == "verb" and "person" in i]
        noun_cands = [i for i in infos if i["type"] == "noun"]
        # A bare Egyptian stem (ꜥnḫ) is both a noun and a verb whose subject is a following noun.
        noun_like = noun_cands and conjugated and all(c.get("noun_subject") for c in conjugated)
        # After an independent pronoun (jnk, ntṯn…) a noun/verb homograph is the predicate noun: ntṯn sš 'you are scribes'.
        pronoun_first = pron_person is not None and not content_seen
        if conjugated and not verb_cands and not noun_like and not (noun_cands and (len(matches) == 1 or pronoun_first)):
            verb_cands, verb_phrase = conjugated, phrase
            copula_alt = next((i["person"] for i in infos if i["type"] == "cop"), None)
            content_seen = True
            continue
        if noun_cands:
            copulas = [c["copula"] for c in noun_cands if c.get("copula")]
            if copulas:
                copula_person = copulas[0]
                if len(set(copulas)) > 1:
                    ambiguities.append(f"'{phrase}' can mean several persons: {', '.join(sorted(set(copulas)))}; {copulas[0]} was used.")
            entry = {"phrase": phrase, "concept": noun_cands[0]["concept"], "roles": {c.get("role") for c in noun_cands},
                     "concepts": list(dict.fromkeys(c["concept"] for c in noun_cands)),
                     "definite": {c.get("definite") for c in noun_cands},
                     "adj": pending_adj if not leading_adj else None, "alt_verb": conjugated if noun_like else None}
            if not leading_adj:
                pending_adj = None
            concepts = {c["concept"] for c in noun_cands}
            if len(concepts) > 1:
                ambiguities.append(f"'{phrase}' matches several nouns: {', '.join(sorted(concepts))}.")
            nouns_seen.append(entry)
            content_seen = True
            continue
        adj_cands = [i for i in infos if i["type"] == "adj"]
        if adj_cands:
            copulas = [c["copula"] for c in adj_cands if c.get("copula")]
            if copulas:
                copula_person = copulas[0]
                if len(set(copulas)) > 1:
                    ambiguities.append(f"'{phrase}' can mean several persons: {', '.join(sorted(set(copulas)))}; {copulas[0]} was used.")
            concept = adj_cands[0]["concept"]
            can_predicate = any(c.get("role") == "predicate" for c in adj_cands)
            indefinite = all(c.get("definite") is False for c in adj_cands)
            if lang in EGYPTIAN and not content_seen and can_predicate:
                predicate_adj, leading_adj = concept, True  # nfr sw, ꜥꜣ nswt: the adjective leads
            elif (nouns_seen and can_predicate and indefinite and nouns_seen[-1]["definite"] == {True}):
                predicate_adj = concept  # aš-šamsu kabīratun: definite subject, indefinite predicate
            elif nouns_seen and nouns_seen[-1]["adj"] is None and lang != "old_amharic":
                nouns_seen[-1]["adj"] = concept
            else:
                pending_adj = concept
            content_seen = True
            continue
        cop = [i for i in infos if i["type"] == "cop"]
        pron = [i for i in infos if i["type"] == "pron"]
        if cop and not (pron and not nouns_seen):
            copula_person = cop[0]["person"]
            cop_negative = cop_negative or any(c.get("negative") for c in cop)
            if any(c.get("pw") for c in cop):
                pw_at = len(nouns_seen)
            continue
        if pron:
            pron_person = pron[0]["person"]
            continue
        citation_verbs += [i["verb"] for i in infos if i["type"] == "verb"]
        # prepositions and idiom fillers carry no extra meaning here

    if pending_adj and nouns_seen:
        nouns_seen[0]["adj"] = nouns_seen[0]["adj"] or pending_adj
        pending_adj = None
    if not verb_cands and len(nouns_seen) >= 2 and nouns_seen[0].get("alt_verb") and not (copula_person or pron_person or pw_at is not None):
        verb_cands, verb_phrase = nouns_seen[0]["alt_verb"], nouns_seen[0]["phrase"]
        nouns_seen = nouns_seen[1:]
    any_adjective = any(i["type"] == "adj" for _, infos in matches for i in infos)
    if verb_cands and copula_alt and (nouns_seen or any_adjective) and not any("object" in n["roles"] for n in nouns_seen):
        # Latin es/estis/est are both 'you are/is' and 'you eat/eats'; a nominative noun or adjective means 'be'.
        ambiguities.append(f"'{verb_phrase}' could also be a form of 'eat'; the nominative favours 'be'.")
        verb_cands, copula_person = [], copula_alt
    if verb_cands:
        # Fused negatives (hakuona, ʾigabra, ʾalsärram, nu-mu-un-du3) carry the negation themselves; with a separate
        # particle, Egyptian n sḏm.f / n sḏm.n.f swap tense, so the negative reading of the form must win.
        neg_cands = [c for c in verb_cands if c.get("negative")]
        pos_cands = [c for c in verb_cands if not c.get("negative")]
        verb_cands = (neg_cands or pos_cands) if negative else (pos_cands or neg_cands)
        negative = negative or any(c.get("negative") for c in verb_cands)
        enough_nouns = len(nouns_seen) >= 2 or (len(nouns_seen) == 1 and not any(not c.get("noun_subject") for c in verb_cands))
        if not enough_nouns:
            verb_cands = [c for c in verb_cands if not c.get("noun_subject")] or verb_cands
        # A form like Egyptian jr.n is both 'we make' and 'made (by NOUN)'; two nouns favour a noun subject.
        third = [c for c in verb_cands if c["person"] in THIRD_PERSON]
        preferred = third if len(nouns_seen) >= 2 and third else verb_cands
        past = [c for c in preferred if c["tense"] == "past"]
        verb_info = (past or preferred)[0]
        readings = sorted({(c["verb"], c["person"], c["tense"]) for c in verb_cands})
        if len(readings) > 1:
            ambiguities.append(f"'{verb_phrase}' can be read several ways: " + "; ".join(f"{v} {p} {t}" for v, p, t in readings) + ".")
        subject: dict[str, Any] = {"person": verb_info["person"]}
        obj = None
        if len(nouns_seen) >= 2:
            first, second = nouns_seen[0], nouns_seen[1]
            subject = {"person": _person_for(first["concept"]), "noun": first["concept"], "adj": first["adj"]}
            obj = {"noun": second["concept"], "adj": second["adj"], "definite": True}
        elif nouns_seen:
            only = nouns_seen[0]
            as_subject = only["roles"] & {"subject", "subject_erg"} and not only["roles"] & {"object"}
            if as_subject and verb_info["person"] in THIRD_PERSON:
                subject = {"person": _person_for(only["concept"]), "noun": only["concept"], "adj": only["adj"]}
            else:
                obj = {"noun": only["concept"], "adj": only["adj"], "definite": True}
        if obj:
            obj["noun"] = _best_concept(nouns_seen[-1], ("object",), verb_info["verb"], lang)
            if lang == "old_arabic" and nouns_seen[-1]["definite"] == {False}:
                obj["definite"] = False
        if subject.get("noun"):
            subject["noun"] = _best_concept(nouns_seen[0], ("subject_erg", "subject"), verb_info["verb"], lang)
            subject["person"] = _person_for(subject["noun"])
        frame = {"kind": "clause", "subject": subject, "verb": verb_info["verb"], "tense": verb_info["tense"], "object": obj}
        return _result(_flag(frame, negative, question), unknown, notes, ambiguities)

    adjectives_seen = [i["concept"] for _, infos in matches for i in infos[:1] if i["type"] == "adj"]
    identity_signal = (copula_person or pron_person or pw_at is not None or predicate_adj or cop_negative
                       or len(nouns_seen) >= 2)
    if identity_signal and (nouns_seen or adjectives_seen):
        person = pron_person or copula_person or "3ms"
        subject = {"person": person}
        predicate: dict[str, Any] | None = None

        def noun_subject(n: dict[str, Any]) -> dict[str, Any]:
            concept = _best_concept(n, ("subject_erg", "subject"), None, lang)
            return {"person": _person_for(concept), "noun": concept}

        def noun_predicate(n: dict[str, Any]) -> dict[str, Any]:
            return {"noun": _best_concept(n, ("predicate",), None, lang), "adj": n["adj"]}

        if pw_at is not None and 0 < pw_at < len(nouns_seen):
            predicate, subject = noun_predicate(nouns_seen[0]), noun_subject(nouns_seen[pw_at])
        elif leading_adj:
            predicate = {"noun": None, "adj": predicate_adj}
            if nouns_seen:
                subject = noun_subject(nouns_seen[0])
        elif len(nouns_seen) >= 2:
            subject, predicate = noun_subject(nouns_seen[0]), noun_predicate(nouns_seen[1])
        elif len(nouns_seen) == 1:
            only = nouns_seen[0]
            if predicate_adj:
                subject, predicate = noun_subject(only), {"noun": None, "adj": predicate_adj}
            elif only["adj"] and pron_person is None and person in THIRD_PERSON:
                subject, predicate = noun_subject(only), {"noun": None, "adj": only["adj"]}
                ambiguities.append(f"This could also mean 'it is a {only['adj']} {only['concept']}'; the subject reading was used.")
            else:
                predicate = noun_predicate(only)
        else:
            predicate = {"noun": None, "adj": predicate_adj or adjectives_seen[0]}
        frame = {"kind": "identity", "subject": subject, "predicate": predicate}
        return _result(_flag(frame, negative or cop_negative, question), unknown, notes, ambiguities)
    if nouns_seen:
        only = nouns_seen[0]
        concept = _best_concept(only, ("citation",), None, lang)
        if only["adj"]:
            if lang == "proto_semitic":
                ambiguities.append("Proto-Semitic nominal sentences have no copula, so this could also mean "
                                   f"'the {only['concept']} is {only['adj']}'.")
            return _result({"kind": "np", "np": {"noun": concept, "adj": only["adj"], "definite": True}}, unknown, notes, ambiguities)
        return _result({"kind": "word", "word_kind": "noun", "concept": concept}, unknown, notes, ambiguities)
    if adjectives_seen:
        return _result({"kind": "word", "word_kind": "adj", "concept": adjectives_seen[0]}, unknown, notes, ambiguities)
    if citation_verbs:
        return _result({"kind": "word", "word_kind": "verb", "concept": citation_verbs[0]}, unknown, notes, ambiguities)
    return _result(None, unknown, notes, ambiguities)


def parse(text: str, lang: str) -> ParseResult:
    if lang == "english":
        return parse_english(text)
    if lang == "swahili":
        return parse_swahili(text)
    if lang not in REALIZERS:
        raise KeyError(lang)
    return parse_ancient(text, lang)
