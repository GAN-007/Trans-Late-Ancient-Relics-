"""Concept lexicon shared by every Ancient Language Ladder realizer and parser."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data" / "ancient" / "lexicon.json"

PERSONS = ["1s", "2ms", "2fs", "3ms", "3fs", "1p", "2p", "3p"]
LATIN_PERSON_INDEX = {"1s": 0, "2ms": 1, "2fs": 1, "3ms": 2, "3fs": 2, "1p": 3, "2p": 4, "3p": 5}
CONFIDENCE_SCORE = {"high": 0.9, "medium": 0.7, "low": 0.45}


@lru_cache(maxsize=1)
def lexicon() -> dict[str, Any]:
    return json.loads(DATA.read_text(encoding="utf-8"))


def nouns() -> dict[str, Any]:
    return lexicon()["nouns"]


def adjectives() -> dict[str, Any]:
    return lexicon()["adjectives"]


def verbs() -> dict[str, Any]:
    return lexicon()["verbs"]


def entry(kind: str, concept: str) -> dict[str, Any] | None:
    table = {"noun": nouns, "adj": adjectives, "verb": verbs}[kind]()
    return table.get(concept)


def form(kind: str, concept: str, lang: str) -> Any:
    item = entry(kind, concept)
    return None if item is None else item.get(lang)


@lru_cache(maxsize=1)
def english_index() -> dict[str, list[tuple[str, str, dict[str, Any]]]]:
    """Map English surface words to (kind, concept, features)."""
    index: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}

    def add(word: str, kind: str, concept: str, **features: Any) -> None:
        index.setdefault(word.lower(), []).append((kind, concept, features))

    for concept, item in nouns().items():
        for word in item["en"]:
            add(word, "noun", concept)
            add(word + "s", "noun", concept, plural=True)
    for concept, item in adjectives().items():
        for word in item["en"]:
            add(word, "adj", concept)
    for concept, item in verbs().items():
        en = item["en"]
        add(en["base"], "verb", concept, tense="present", s3=False)
        add(en["s3"], "verb", concept, tense="present", s3=True)
        add(en["past"], "verb", concept, tense="past")
        add(en["pp"], "verb", concept, tense="past", participle=True)
        if en["base"].endswith("e"):
            add(en["base"][:-1] + "ing", "verb", concept, tense="present", progressive=True)
        else:
            add(en["base"] + "ing", "verb", concept, tense="present", progressive=True)
    return index


@lru_cache(maxsize=1)
def swahili_index() -> dict[str, list[tuple[str, str]]]:
    index: dict[str, list[tuple[str, str]]] = {}
    for concept, item in nouns().items():
        index.setdefault(item["sw"]["f"].lower(), []).append(("noun", concept))
    for concept, item in verbs().items():
        index.setdefault("verb:" + item["sw"]["root"], []).append(("verb", concept))
    return index


def swahili_adjective(stem: str, prefix: str) -> str:
    """Attach a Swahili adjective concord prefix (nyumba nzuri, mtu mzuri, maji mazuri)."""
    if prefix == "n":
        if stem[0] in "kptsfch":
            return stem
        if stem[0] in "aeiou":
            return "ny" + stem
        return "n" + stem
    if prefix == "m" and stem[0] in "aeiou":
        return "mw" + stem
    if prefix == "" and stem[0] in "aeiou":
        return "j" + stem
    return prefix + stem


def swahili_adjectives() -> dict[str, str]:
    return {concept: item["sw"] for concept, item in adjectives().items()}
