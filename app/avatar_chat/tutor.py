"""Tutor mode: after a reading, the guide quizzes the learner like a teacher would.

The guide points at a word (the card highlights it) and asks the learner to
say it or to say what it means, checks the answer tolerantly (speech
recognition mishears ancient words), corrects gently, and keeps score.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

START = re.compile(r"\b(?:quiz\s+me|test\s+me|let\s+me\s+try|practi[cs]e|nijaribu|nipe\s+(?:jaribio|maswali)|nifanyishe)\b", re.I)
STOP = re.compile(r"\b(?:stop(?:\s+the)?\s+quiz|end\s+(?:the\s+)?quiz|enough|that'?s\s+enough|acha|basi|imetosha)\b", re.I)
SKIP = re.compile(r"\b(?:skip|pass|i\s+don'?t\s+know|sijui|ruka)\b", re.I)
REPEAT = re.compile(r"\b(?:repeat|again\s+please|say\s+(?:it\s+)?again|rudia)\b", re.I)
READ_AGAIN = re.compile(r"\b(?:read\s+(?:it\s+)?again|read\s+it\s+(?:to\s+me|word\s+by\s+word)|word\s+by\s+word|teach\s+me\s+(?:to\s+read\s+)?(?:it|this)|soma\s+tena|nisomee|nifundishe|neno\s+kwa\s+neno)\b", re.I)
SLOWER = re.compile(r"\b(?:slower|slow\s+down|more\s+slowly|polepole|taratibu)\b", re.I)
FASTER = re.compile(r"\b(?:faster|speed\s+up|haraka)\b", re.I)
WORD_N = re.compile(r"\b(?:word|neno(?:\s+la)?)\s+(?:number\s+)?(\d{1,2})\b", re.I)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ꜣ", "a").replace("ꜥ", "a").replace("ʾ", "").replace("ʿ", "").replace("ə", "e")
    return re.sub(r"[^a-z]", "", text)


def similar(answer: str, expected: str) -> float:
    a, b = normalize(answer), normalize(expected)
    if not a or not b:
        return 0.0
    if b in a:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def meaning_matches(answer: str, glosses: list[str]) -> bool:
    words = set(re.findall(r"[a-z]+", unicodedata.normalize("NFC", answer.lower())))
    for gloss in glosses:
        gloss_words = [w for w in re.findall(r"[a-z]+", gloss.lower()) if w not in {"the", "a", "an", "to", "i", "ku"}]
        if gloss_words and all(w in words or any(similar(x, w) > 0.84 for x in words) for w in gloss_words):
            return True
        if gloss and similar(answer, gloss) > 0.84:
            return True
    return False


@dataclass
class Quiz:
    order: list[int]
    position: int = 0
    mode: str = "say"  # say | meaning
    attempts: int = 0
    score: int = 0
    asked: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def current(self) -> int | None:
        return self.order[self.position] if self.position < len(self.order) else None


def quizable(reading: dict[str, Any]) -> list[int]:
    return [i for i, s in enumerate(reading.get("segments", [])) if s.get("pronunciation") and (s["meaning"].get("english") or s["meaning"].get("swahili"))]


def _question(reading: dict[str, Any], quiz: Quiz, lang: str) -> dict[str, Any]:
    index = quiz.current
    en = lang == "english"
    number = (index or 0) + 1
    if quiz.mode == "say":
        text = (f"Look at word {number}. How do you say it?" if en else f"Angalia neno la {number}. Unalitamkaje?")
    else:
        text = (f"And what does word {number} mean?" if en else f"Na neno la {number} lina maana gani?")
    return {"text": text, "segment": index}


def start(reading: dict[str, Any], lang: str) -> tuple[Quiz | None, list[dict[str, Any]]]:
    order = quizable(reading)
    en = lang == "english"
    if not order:
        return None, [{"text": "There are no confirmed words in this reading that I can quiz you on yet." if en
                       else "Hakuna maneno yaliyothibitishwa katika usomaji huu ninayoweza kukuuliza.", "segment": None}]
    quiz = Quiz(order=order)
    intro = (f"Let's practise. I'll point at each word; you read it to me. There are {len(order)} words." if en
             else f"Tufanye mazoezi. Nitaonyesha kila neno; wewe unisomee. Kuna maneno {len(order)}.")
    return quiz, [{"text": intro, "segment": None, "quiz": "start"}, _question(reading, quiz, lang)]


def _advance(reading: dict[str, Any], quiz: Quiz, lang: str) -> list[dict[str, Any]]:
    quiz.attempts = 0
    if quiz.mode == "say":
        quiz.mode = "meaning"
        return [_question(reading, quiz, lang)]
    quiz.mode = "say"
    quiz.position += 1
    if quiz.current is None:
        return finish(quiz, lang)
    return [_question(reading, quiz, lang)]


def finish(quiz: Quiz, lang: str) -> list[dict[str, Any]]:
    en = lang == "english"
    total = max(1, quiz.asked)
    if quiz.score == quiz.asked and quiz.asked:
        verdict = "Perfect! You read every word." if en else "Safi kabisa! Umesoma kila neno."
    elif quiz.score >= total / 2:
        verdict = "Well done, that's real progress." if en else "Hongera, umepiga hatua kubwa."
    else:
        verdict = "Good effort. Reading takes practice; let's go again soon." if en else "Juhudi nzuri. Kusoma kunahitaji mazoezi; tutarudia hivi karibuni."
    summary = (f"You got {quiz.score} out of {quiz.asked}. {verdict}" if en else f"Umepata {quiz.score} kati ya {quiz.asked}. {verdict}")
    return [{"text": summary, "segment": None, "quiz_done": True}]


def answer(reading: dict[str, Any], quiz: Quiz, text: str, lang: str) -> list[dict[str, Any]]:
    en = lang == "english"
    if SKIP.search(text):
        quiz.asked += 1
        return reveal(reading, quiz, lang) + _advance(reading, quiz, lang)
    segment = reading["segments"][quiz.current]
    quiz.attempts += 1
    if quiz.mode == "say":
        best = max(similar(text, segment["pronunciation"]), similar(text, segment["transliteration"]))
        correct = best >= 0.72
    else:
        glosses = [segment["meaning"].get("english", ""), segment["meaning"].get("swahili", "")]
        correct = meaning_matches(text, [g for g in glosses if g])
    quiz.history.append({"segment": quiz.current, "mode": quiz.mode, "answer": text, "correct": correct})
    if correct:
        quiz.asked += 1
        quiz.score += 1
        praise = ["Yes, exactly!", "That's right!", "Very good!", "Perfect."] if en else ["Ndiyo, sawasawa!", "Sahihi!", "Vizuri sana!", "Safi."]
        return [{"text": praise[quiz.score % len(praise)], "segment": quiz.current, "correct": True}] + _advance(reading, quiz, lang)
    if quiz.attempts < 2:
        if quiz.mode == "say":
            hint = segment["pronunciation"][:2]
            return [{"text": (f"Not quite. Here's a hint: it starts with {hint}. Try once more." if en
                              else f"Bado kidogo. Kidokezo: linaanza na {hint}. Jaribu tena."), "segment": quiz.current, "correct": False}]
        return [{"text": ("Not quite. Think about the picture the signs make, and try once more." if en
                          else "Bado kidogo. Fikiria picha ambayo alama zinaunda, kisha ujaribu tena."), "segment": quiz.current, "correct": False}]
    quiz.asked += 1
    return reveal(reading, quiz, lang) + _advance(reading, quiz, lang)


def reveal(reading: dict[str, Any], quiz: Quiz, lang: str) -> list[dict[str, Any]]:
    en = lang == "english"
    segment = reading["segments"][quiz.current]
    if quiz.mode == "say":
        syllables = "-".join(re.findall(r"[^aeiou]*[aeiou]+(?:[^aeiou]+$)?", segment["pronunciation"])) or segment["pronunciation"]
        return [{"text": (f"It's said {segment['pronunciation']}. Say it with me: {syllables}." if en
                          else f"Linatamkwa {segment['pronunciation']}. Sema nami: {syllables}."), "segment": quiz.current, "correct": False}]
    meaning = segment["meaning"].get(lang) or segment["meaning"].get("english")
    return [{"text": (f"It means {meaning}." if en else f"Maana yake ni {meaning}."), "segment": quiz.current, "correct": False}]


def repeat(reading: dict[str, Any], quiz: Quiz, lang: str) -> list[dict[str, Any]]:
    return [_question(reading, quiz, lang)]
