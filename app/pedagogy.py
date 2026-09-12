from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

from .egyptian import current_lexicon
from .runtime import connect

DATA = Path(__file__).parent / "data"


def lessons() -> list[dict]:
    items: list[dict] = []
    split_dir = DATA / "lessons"
    if split_dir.exists():
        for path in sorted(split_dir.glob("*.json")):
            items.extend(json.loads(path.read_text(encoding="utf-8")))
    else:
        legacy = DATA / "lessons.json"
        if legacy.exists():
            items.extend(json.loads(legacy.read_text(encoding="utf-8")))
    return sorted(items, key=lambda x: x["id"])


def get_lesson(lesson_id: int):
    return next((lesson for lesson in lessons() if lesson["id"] == lesson_id), None)


def ensure_progress_db() -> None:
    conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS progress(
            learner TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(learner, item_type, item_id)
        )
        """
    )
    conn.commit()
    conn.close()


def save_progress(learner: str, item_type: str, item_id: str, score: float):
    ensure_progress_db()
    conn = connect()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO progress(learner,item_type,item_id,score,attempts,updated_at)
        VALUES(?,?,?,?,1,?)
        ON CONFLICT(learner,item_type,item_id)
        DO UPDATE SET score=excluded.score, attempts=progress.attempts+1, updated_at=excluded.updated_at
        """,
        (learner,item_type,item_id,float(score),now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT learner,item_type,item_id,score,attempts,updated_at FROM progress WHERE learner=? AND item_type=? AND item_id=?",
        (learner,item_type,item_id),
    ).fetchone()
    conn.close()
    return dict(row)


def get_progress(learner: str):
    ensure_progress_db()
    conn = connect()
    rows = conn.execute(
        "SELECT learner,item_type,item_id,score,attempts,updated_at FROM progress WHERE learner=? ORDER BY updated_at DESC",
        (learner,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def random_vocab_quiz(language: str="english", count: int=10):
    pool=[e for e in current_lexicon() if e.get(language)]
    random.shuffle(pool)
    result=[]
    for e in pool[:count]:
        correct=e[language][0]
        distractors=[]
        candidates=[x for x in pool if x is not e and x.get(language)]
        random.shuffle(candidates)
        for x in candidates:
            option=x[language][0]
            if option != correct and option not in distractors:
                distractors.append(option)
            if len(distractors)==3:
                break
        choices=distractors+[correct]
        random.shuffle(choices)
        result.append({
            "id":e["transliteration"],
            "prompt":f"What does '{e['transliteration']}' mean?",
            "choices":choices,
            "answer":correct,
            "hieroglyphs":e.get("hieroglyphs","")
        })
    return result
