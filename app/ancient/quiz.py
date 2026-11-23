"""Quizzes for every rung of the Ancient Language Ladder.

Three kinds of question, all generated from the same grammar that translates:

* meaning  - see the ancient word (and its script), pick what it means
* form     - see the meaning, pick the ancient word
* sentence - see a composed ancient sentence, pick its meaning; the wrong answers differ
             only in negation, tense, person or a noun, so the learner must actually read it
"""
from __future__ import annotations

import random
from typing import Any

from .engine import LADDER_ORDER, LadderError, language_id
from .grammar import REALIZERS
from .lexicon import adjectives, nouns, verbs

EXPLAIN = {"english", "swahili"}
NO_SENTENCES = {"proto_world", "archaic_hieroglyphic"}
SENTENCE_NOUNS = ["king", "woman", "scribe", "god", "servant", "man", "child"]
SENTENCE_OBJECTS = ["house", "temple", "river", "water", "bread", "name", "truth", "city"]
TRANSITIVE = ["see", "make", "build", "love", "write", "hear", "protect", "give", "know", "eat"]


def _word_items(lang: str, explain: str) -> list[dict[str, Any]]:
    items = []
    for kind, table in (("noun", nouns()), ("adj", adjectives()), ("verb", verbs())):
        for concept in table:
            frame = {"kind": "word", "word_kind": kind, "concept": concept}
            out = REALIZERS[lang].realize(frame)
            if not out["ok"] or not out["text"]:
                continue
            meaning = REALIZERS[explain].realize(frame)["text"]
            items.append({"concept": concept, "kind": kind, "form": out["text"], "scripts": out["scripts"],
                          "status": out["status"], "meaning": meaning, "notes": out["notes"][:2]})
    return items


def _choices(correct: str, pool: list[str], rng: random.Random, size: int = 4) -> list[str]:
    distractors = [p for p in dict.fromkeys(pool) if p != correct]
    rng.shuffle(distractors)
    choices = distractors[: size - 1] + [correct]
    rng.shuffle(choices)
    return choices


def _sentence_frame(rng: random.Random) -> dict[str, Any]:
    if rng.random() < 0.7:
        subject: dict[str, Any] = ({"person": rng.choice(["1s", "2ms", "3ms", "3fs", "1p", "3p"])} if rng.random() < 0.4 else
                                   {"person": "3ms", "noun": rng.choice(SENTENCE_NOUNS), "adj": None})
        if subject.get("noun") == "woman":
            subject["person"] = "3fs"
        frame = {"kind": "clause", "subject": subject, "verb": rng.choice(TRANSITIVE), "tense": rng.choice(["past", "present"]),
                 "object": {"noun": rng.choice(SENTENCE_OBJECTS), "adj": rng.choice([None, None, "great", "good"]), "definite": True}}
    else:
        noun = rng.choice(SENTENCE_NOUNS)
        frame = {"kind": "identity", "subject": {"person": "3fs" if noun == "woman" else "3ms", "noun": noun},
                 "predicate": rng.choice([{"noun": None, "adj": rng.choice(["great", "good"])}, {"noun": "servant", "adj": None}])}
    if rng.random() < 0.4:
        frame["negative"] = True
    if rng.random() < 0.2:
        frame["question"] = True
    return frame


def _variants(frame: dict[str, Any]) -> list[dict[str, Any]]:
    """Near-miss meanings: flip one feature at a time."""
    out = []
    flipped = dict(frame)
    flipped["negative"] = not frame.get("negative")
    out.append(flipped)
    if frame["kind"] == "clause":
        out.append({**frame, "tense": "present" if frame["tense"] == "past" else "past"})
        subject = frame["subject"]
        swap = {"person": "1s"} if subject.get("noun") else {"person": "3ms", "noun": "king", "adj": None}
        out.append({**frame, "subject": swap})
        other = next(n for n in SENTENCE_OBJECTS if n != frame["object"]["noun"])
        out.append({**frame, "object": {**frame["object"], "noun": other}})
    else:
        other = next(n for n in SENTENCE_NOUNS if n != frame["subject"]["noun"])
        out.append({**frame, "subject": {"person": "3fs" if other == "woman" else "3ms", "noun": other}})
        predicate = frame["predicate"]
        out.append({**frame, "predicate": {"noun": None, "adj": "good" if predicate.get("adj") == "great" else "great"}})
    out.append({**frame, "question": not frame.get("question")})
    return out


def _sentence_items(lang: str, explain: str, count: int, rng: random.Random) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _ in range(count * 15):
        if len(items) >= count:
            break
        frame = _sentence_frame(rng)
        out = REALIZERS[lang].realize(frame)
        if not out["ok"] or out["text"] in seen:
            continue
        correct = REALIZERS[explain].realize(frame)["text"]
        wrong = []
        for variant in _variants(frame):
            text = REALIZERS[explain].realize(variant)["text"]
            # a distractor must look different in the ancient language too, or the question is unfair
            if text != correct and REALIZERS[lang].realize(variant)["text"] != out["text"]:
                wrong.append(text)
        if len(set(wrong)) < 3:
            continue
        seen.add(out["text"])
        items.append({"kind": "sentence", "prompt_text": out["text"], "scripts": out["scripts"], "status": out["status"],
                      "choices": _choices(correct, wrong, rng), "answer": correct, "notes": out["notes"][:3]})
    return items


def make_quiz(language: str, explain: str = "english", mode: str = "mixed", count: int = 10, seed: int | None = None) -> dict[str, Any]:
    lang = language_id(language)
    if lang == "english" or lang not in REALIZERS:
        raise LadderError("Choose an ancient language (or Swahili) to be quizzed on.")
    explain = explain if explain in EXPLAIN else "english"
    if explain == lang:
        explain = "english"
    if mode not in {"meaning", "form", "sentence", "mixed"}:
        raise LadderError("mode must be meaning, form, sentence or mixed.")
    count = max(1, min(int(count), 30))
    rng = random.Random(seed)
    words = _word_items(lang, explain)
    if not words:
        raise LadderError(f"No vocabulary is available for {REALIZERS[lang].name}.")
    modes = [mode] if mode != "mixed" else (["meaning", "form", "sentence"] if lang not in NO_SENTENCES else ["meaning", "form"])
    if mode == "sentence" and lang in NO_SENTENCES:
        raise LadderError(f"{REALIZERS[lang].name} has no sentences to quiz: {REALIZERS[lang].notes[0] if REALIZERS[lang].notes else ''}")
    questions: list[dict[str, Any]] = []
    per = {m: count // len(modes) + (1 if i < count % len(modes) else 0) for i, m in enumerate(modes)}
    if "sentence" in per:
        questions += _sentence_items(lang, explain, per["sentence"], rng)
    word_modes = [m for m in modes if m != "sentence"]
    shortfall = count - len(questions) - sum(per.get(m, 0) for m in word_modes)
    picks = rng.sample(words, min(len(words), sum(per.get(m, 0) for m in word_modes) + max(0, shortfall)))
    for index, item in enumerate(picks):
        kind = word_modes[index % len(word_modes)] if word_modes else "meaning"
        same_kind = [w for w in words if w["kind"] == item["kind"]] or words
        if kind == "meaning":
            questions.append({"kind": "meaning", "prompt_text": item["form"], "scripts": item["scripts"], "status": item["status"],
                              "choices": _choices(item["meaning"], [w["meaning"] for w in same_kind], rng), "answer": item["meaning"],
                              "notes": item["notes"]})
        else:
            questions.append({"kind": "form", "prompt_text": item["meaning"], "scripts": {}, "status": item["status"],
                              "choices": _choices(item["form"], [w["form"] for w in same_kind], rng), "answer": item["form"],
                              "notes": item["notes"]})
    rng.shuffle(questions)
    for number, q in enumerate(questions, 1):
        q["id"] = number
    realizer = REALIZERS[lang]
    return {"language": lang, "language_name": realizer.name, "status": realizer.status, "explain": explain, "mode": mode,
            "questions": questions[:count],
            "note": ("Sentences are composed by the ladder's grammar rules, not quoted from ancient texts."
                     if realizer.status == "attested" else realizer.notes[0] if realizer.notes else "")}


def quiz_languages() -> list[dict[str, Any]]:
    return [{"id": lang, "name": REALIZERS[lang].name, "sentences": lang not in NO_SENTENCES}
            for lang in LADDER_ORDER if lang != "english"]
