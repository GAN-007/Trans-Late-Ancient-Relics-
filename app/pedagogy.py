from __future__ import annotations

import json
import random
from pathlib import Path

from .egyptian import all_lexicon_entries

DATA = Path(__file__).parent / "data"


def lessons() -> list[dict]:
    directory = DATA / "lessons"
    items: list[dict] = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            items.extend(json.loads(path.read_text(encoding="utf-8")))
    elif (DATA / "lessons.json").exists():
        items.extend(json.loads((DATA / "lessons.json").read_text(encoding="utf-8")))
    return sorted(items, key=lambda x: x["id"])


def get_lesson(lesson_id: int) -> dict | None:
    return next((lesson for lesson in lessons() if lesson["id"] == lesson_id), None)


def random_vocab_quiz(language: str = "english", count: int = 10) -> list[dict]:
    pool = [e for e in all_lexicon_entries() if e.get(language)]
    random.shuffle(pool)
    result = []
    for e in pool[:count]:
        correct = e[language][0]
        distractors = []
        candidates = [x for x in pool if x is not e and x.get(language)]
        random.shuffle(candidates)
        for x in candidates:
            option = x[language][0]
            if option != correct and option not in distractors:
                distractors.append(option)
            if len(distractors) == 3:
                break
        choices = distractors + [correct]
        random.shuffle(choices)
        result.append({
            "id": e["transliteration"],
            "prompt": f"What does '{e['transliteration']}' mean?",
            "choices": choices,
            "answer": correct,
            "hieroglyphs": e.get("hieroglyphs", ""),
        })
    return result
