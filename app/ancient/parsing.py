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


def _result(frame: Frame | None, unknown: list[str], notes: list[str], ambiguities: list[str] | None = None) -> ParseResult:
    return ParseResult(frame=frame, unknown=unknown, notes=notes, ambiguities=ambiguities or [])


# ======================================================================= English
FEMALE_NOUNS = {"woman", "mother"}
EN_PRONOUNS = {"i": "1s", "you": "2ms", "he": "3ms", "she": "3fs", "we": "1p", "they": "3p"}
EN_COPULA = {"am", "is", "are", "was", "were"}
EN_ARTICLES = {"the", "a", "an"}
EN_PREPS = {"in", "to", "into", "at", "toward", "towards", "on", "upon"}
EN_CONTRACTIONS = {"i'm": "i am", "i've": "i have", "you're": "you are", "we're": "we are", "they're": "they are",
                   "he's": "he is", "she's": "she is", "we've": "we have", "they've": "they have", "you've": "you have"}
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
            return {"noun": noun_hit[1], "adj": adj, "definite": definite}, i + 1
        break
    if i < len(words) and words[i] not in EN_PREPS and not english_index().get(words[i]):
        unknown.append(words[i])
        return None, i + 1
    if adj:
        return {"noun": None, "adj": adj, "definite": definite}, i
    return None, i


def parse_english(text: str) -> ParseResult:
    notes: list[str] = []
    unknown: list[str] = []
    t = unicodedata.normalize("NFC", text.strip().lower()).replace("’", "'")
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
            subject, i = {"person": "3ms", "noun": np["noun"], "adj": np.get("adj")}, j
        elif np and j >= len(words):
            return _result({"kind": "np", "np": np}, unknown, notes)

    tense = "present"
    if i < len(words) and words[i] in {"have", "has", "had", "did"}:
        tense = "past"
        i += 1
    elif i < len(words) and words[i] in {"do", "does"}:
        i += 1
    elif i < len(words) and words[i] in {"will", "shall"}:
        notes.append("Future tense is not modelled; the present/imperfective is used.")
        i += 1

    if i < len(words) and words[i] in EN_COPULA and subject and not subject.get("noun"):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if not any(h[0] == "verb" for h in english_index().get(nxt, [])):
            np, _ = _english_np(words, i + 1, unknown)
            if np and np.get("noun"):
                return _result({"kind": "identity", "subject": subject, "predicate": {"noun": np["noun"], "adj": np.get("adj")}}, unknown, notes)
        else:
            tense = "past" if words[i] in {"was", "were"} else tense
            i += 1

    verb = None
    while i < len(words):
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
        return _result(None, unknown, notes)
    if subject is None:
        subject = {"person": "3ms"}
    if subject.get("noun"):
        subject["person"] = "3fs" if subject["noun"] in FEMALE_NOUNS else "3ms"
    while i < len(words) and words[i] in EN_PREPS:
        i += 1
    obj = None
    if i < len(words):
        obj, i = _english_np(words, i, unknown)
    unknown += [w for w in words[i:] if w not in EN_PREPS]
    if topic and not obj:
        obj = topic
    frame = {"kind": "clause", "subject": subject, "verb": verb, "tense": tense, "object": obj}
    return _result(frame, unknown, notes)


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


def parse_swahili(text: str) -> ParseResult:
    notes: list[str] = []
    unknown: list[str] = []
    words = re.findall(r"[a-z']+", unicodedata.normalize("NFC", text.lower()))
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
    subject: dict[str, Any] | None = None
    verb = tense = None
    obj: dict[str, Any] | None = None
    pending_noun: dict[str, Any] | None = None
    copula = False
    for w in words:
        if w in SW_PRONOUNS and subject is None:
            subject = {"person": SW_PRONOUNS[w]}
            continue
        if w == "ni" and verb is None:
            copula = True
            continue
        noun_key = w if w in noun_map else (w[:-2] if w.endswith("ni") and w[:-2] in noun_map else None)
        if noun_key:
            np = {"noun": noun_map[noun_key], "adj": None, "definite": True}
            if verb is None and not copula:
                pending_noun = np
            else:
                obj = np
            continue
        if w in adj_map:
            target = obj if obj is not None else pending_noun
            if target is not None:
                target["adj"] = adj_map[w]
            continue
        m = SW_VERB.match(w)
        if m and verb is None:
            root = m.group(4)
            if root not in verb_map and m.group(3):
                root = m.group(3) + root
            if root in verb_map:
                verb = verb_map[root]
                tense = SW_TENSE[m.group(2)]
                if m.group(2) == "ta":
                    notes.append("Swahili future -ta- is mapped to the present/imperfective.")
                if pending_noun is not None:
                    subject = {"person": "3ms", "noun": pending_noun["noun"], "adj": pending_noun.get("adj")}
                    if subject["noun"] in FEMALE_NOUNS:
                        subject["person"] = "3fs"
                    pending_noun = None
                elif subject is None:
                    subject = {"person": SW_SUBJECT.get(m.group(1), "3ms")}
                continue
        unknown.append(w)
    if copula and subject and (obj or pending_noun):
        pred = obj or pending_noun
        return _result({"kind": "identity", "subject": subject, "predicate": {"noun": pred["noun"], "adj": pred.get("adj")}}, unknown, notes)
    if verb:
        if subject and subject.get("person") == "3ms" and not subject.get("noun"):
            notes.append("Swahili a- does not mark gender; masculine was used where a language requires a choice.")
        return _result({"kind": "clause", "subject": subject or {"person": "3ms"}, "verb": verb, "tense": tense, "object": obj}, unknown, notes)
    if pending_noun:
        return _result({"kind": "np", "np": pending_noun}, unknown, notes)
    return _result(None, unknown, notes)


# ============================================================ ancient languages
def _exact_key(text: str) -> str:
    text = re.sub(r"[*።]", "", unicodedata.normalize("NFC", text.lower()))
    return re.sub(r"[\s፡·,]+", " ", text).strip()


def _person_for(noun: str) -> str:
    return "3fs" if noun in FEMALE_NOUNS else "3ms"


def _synthetic_frames(lang: str) -> list[Frame]:
    frames: list[Frame] = []
    noun_ids = list(nouns())
    verb_ids = list(verbs())
    for verb in verb_ids:
        for person in PERSONS:
            for tense in ("past", "present"):
                frames.append({"kind": "clause", "subject": {"person": person}, "verb": verb, "tense": tense, "object": None})
    for noun in noun_ids:
        frames.append({"kind": "word", "word_kind": "noun", "concept": noun})
        for adj in (None, *adjectives()):
            frames.append({"kind": "np", "np": {"noun": noun, "adj": adj, "definite": True}})
            for verb in verb_ids:
                frames.append({"kind": "clause", "subject": {"person": "1s"}, "verb": verb, "tense": "past",
                               "object": {"noun": noun, "adj": adj, "definite": True}})
            for verb in ("make", "go"):
                for tense in ("past", "present"):
                    frames.append({"kind": "clause", "subject": {"person": _person_for(noun), "noun": noun, "adj": adj}, "verb": verb, "tense": tense, "object": None})
        for person in PERSONS:
            frames.append({"kind": "identity", "subject": {"person": person}, "predicate": {"noun": noun, "adj": None}})
        for adj in adjectives():
            frames.append({"kind": "identity", "subject": {"person": "1s"}, "predicate": {"noun": noun, "adj": adj}})
    for verb in verb_ids:
        for tense in ("past", "present"):
            for noun in ("king", "woman", "sun", "sky"):
                frames.append({"kind": "clause", "subject": {"person": _person_for(noun), "noun": noun, "adj": None}, "verb": verb, "tense": tense, "object": None})
    for adj in adjectives():
        frames.append({"kind": "word", "word_kind": "adj", "concept": adj})
        for person in PERSONS:
            frames.append({"kind": "identity", "subject": {"person": person}, "predicate": {"noun": "king", "adj": adj}})
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


def parse_ancient(text: str, lang: str) -> ParseResult:
    exact, loose = form_index(lang)
    words = _split_words(text)
    matches: list[tuple[str, list[dict[str, Any]]]] = []
    unknown: list[str] = []
    i = 0
    while i < len(words):
        found = None
        for index, keyer in ((exact, _exact_key), (loose, loose_key)):
            for n in (3, 2, 1):
                if i + n > len(words):
                    continue
                phrase = " ".join(words[i:i + n])
                key = keyer(phrase)
                if key in index:
                    found = (n, phrase, index[key])
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
    result = _assemble(matches, unknown, lang)
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


def _assemble(matches: list[tuple[str, list[dict[str, Any]]]], unknown: list[str], lang: str) -> ParseResult:
    notes: list[str] = []
    ambiguities: list[str] = []
    verb_phrase = None
    verb_cands: list[dict[str, Any]] = []
    nouns_seen: list[dict[str, Any]] = []
    copula_person = None
    pron_person = None
    pending_adj = None
    copula_alt = None
    citation_verbs: list[str] = []
    for phrase, infos in matches:
        conjugated = [i for i in infos if i["type"] == "verb" and "person" in i]
        noun_cands = [i for i in infos if i["type"] == "noun"]
        # A bare Egyptian stem (ꜥnḫ) is both a noun and a verb whose subject is a following noun.
        noun_like = noun_cands and conjugated and all(c.get("noun_subject") for c in conjugated)
        if conjugated and not verb_cands and not noun_like and not (noun_cands and len(matches) == 1):
            verb_cands, verb_phrase = conjugated, phrase
            copula_alt = next((i["person"] for i in infos if i["type"] == "cop"), None)
            continue
        if noun_cands:
            copulas = [c["copula"] for c in noun_cands if c.get("copula")]
            if copulas:
                copula_person = copulas[0]
            entry = {"phrase": phrase, "concept": noun_cands[0]["concept"], "roles": {c.get("role") for c in noun_cands},
                     "concepts": list(dict.fromkeys(c["concept"] for c in noun_cands)),
                     "adj": pending_adj, "alt_verb": conjugated if noun_like else None}
            pending_adj = None
            concepts = {c["concept"] for c in noun_cands}
            if len(concepts) > 1:
                ambiguities.append(f"'{phrase}' matches several nouns: {', '.join(sorted(concepts))}.")
            nouns_seen.append(entry)
            continue
        adj_cands = [i for i in infos if i["type"] == "adj"]
        if adj_cands:
            copulas = [c["copula"] for c in adj_cands if c.get("copula")]
            if copulas:
                copula_person = copulas[0]
            if nouns_seen and nouns_seen[-1]["adj"] is None and lang != "old_amharic":
                nouns_seen[-1]["adj"] = adj_cands[0]["concept"]
            else:
                pending_adj = adj_cands[0]["concept"]
            continue
        cop = [i for i in infos if i["type"] == "cop"]
        if cop:
            copula_person = cop[0]["person"]
            continue
        pron = [i for i in infos if i["type"] == "pron"]
        if pron:
            pron_person = pron[0]["person"]
            continue
        citation_verbs += [i["verb"] for i in infos if i["type"] == "verb"]
        # prepositions and idiom fillers carry no extra meaning here

    if pending_adj and nouns_seen:
        nouns_seen[0]["adj"] = nouns_seen[0]["adj"] or pending_adj
    if not verb_cands and len(nouns_seen) >= 2 and nouns_seen[0].get("alt_verb") and not (copula_person or pron_person):
        verb_cands, verb_phrase = nouns_seen[0]["alt_verb"], nouns_seen[0]["phrase"]
        nouns_seen = nouns_seen[1:]
    if verb_cands and copula_alt and nouns_seen and not any("object" in n["roles"] for n in nouns_seen):
        # Latin estis/est are both 'you are/is' and 'you eat/eats'; a nominative noun means 'be'.
        ambiguities.append(f"'{verb_phrase}' could also be a form of 'eat'; the nominative noun favours 'be'.")
        verb_cands, copula_person = [], copula_alt
    if verb_cands:
        enough_nouns = len(nouns_seen) >= 2 or (len(nouns_seen) == 1 and not any(not c.get("noun_subject") for c in verb_cands))
        if not enough_nouns:
            verb_cands = [c for c in verb_cands if not c.get("noun_subject")] or verb_cands
        # A form like Egyptian jr.n is both 'we make' and 'made (by NOUN)'; two nouns favour a noun subject.
        third = [c for c in verb_cands if c["person"] in {"3ms", "3fs"}]
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
            if as_subject and verb_info["person"] in {"3ms", "3fs"}:
                subject = {"person": _person_for(only["concept"]), "noun": only["concept"], "adj": only["adj"]}
            else:
                obj = {"noun": only["concept"], "adj": only["adj"], "definite": True}
        if obj:
            obj["noun"] = _best_concept(nouns_seen[-1], ("object",), verb_info["verb"], lang)
        if subject.get("noun"):
            subject["noun"] = _best_concept(nouns_seen[0], ("subject_erg", "subject"), verb_info["verb"], lang)
            subject["person"] = _person_for(subject["noun"])
        frame = {"kind": "clause", "subject": subject, "verb": verb_info["verb"], "tense": verb_info["tense"], "object": obj}
        return _result(frame, unknown, notes, ambiguities)
    if nouns_seen and (copula_person or pron_person):
        person = copula_person or pron_person
        predicate = nouns_seen[0]
        concept = _best_concept(predicate, ("predicate",), None, lang)
        return _result({"kind": "identity", "subject": {"person": person}, "predicate": {"noun": concept, "adj": predicate["adj"]}}, unknown, notes, ambiguities)
    if nouns_seen:
        only = nouns_seen[0]
        concept = _best_concept(only, ("citation",), None, lang)
        if only["adj"]:
            return _result({"kind": "np", "np": {"noun": concept, "adj": only["adj"], "definite": True}}, unknown, notes, ambiguities)
        return _result({"kind": "word", "word_kind": "noun", "concept": concept}, unknown, notes, ambiguities)
    adj_only = [i for _, infos in matches for i in infos if i["type"] == "adj"]
    if adj_only:
        return _result({"kind": "word", "word_kind": "adj", "concept": adj_only[0]["concept"]}, unknown, notes, ambiguities)
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
