from __future__ import annotations
import json, os, random, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .egyptian import LEXICON

DATA = Path(__file__).parent / "data"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_DIR = Path(os.environ.get("ESHB_RUNTIME_DIR", PROJECT_ROOT / "data-runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
DB = Path(os.environ.get("ESHB_DB_PATH", RUNTIME_DIR / "tutor_progress.sqlite3"))

def lessons():
    items = []
    for path in sorted((DATA / "lessons").glob("*.json")):
        items.extend(json.loads(path.read_text(encoding="utf-8")))
    return sorted(items, key=lambda x: x["id"])

def get_lesson(lesson_id: int):
    for lesson in lessons():
        if lesson["id"] == lesson_id:
            return lesson
    return None

def ensure_db():
    conn = sqlite3.connect(DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS progress(
            learner TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_id TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(learner, item_type, item_id)
        )
    """)
    conn.commit()
    return conn

def save_progress(learner: str, item_type: str, item_id: str, score: float):
    conn = ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO progress(learner,item_type,item_id,score,attempts,updated_at)
        VALUES(?,?,?,?,1,?)
        ON CONFLICT(learner,item_type,item_id)
        DO UPDATE SET score=excluded.score, attempts=progress.attempts+1, updated_at=excluded.updated_at
    """,(learner,item_type,item_id,float(score),now))
    conn.commit()
    row = conn.execute("SELECT learner,item_type,item_id,score,attempts,updated_at FROM progress WHERE learner=? AND item_type=? AND item_id=?",(learner,item_type,item_id)).fetchone()
    conn.close()
    return dict(zip(["learner","item_type","item_id","score","attempts","updated_at"],row))

def get_progress(learner: str):
    conn = ensure_db()
    rows = conn.execute("SELECT learner,item_type,item_id,score,attempts,updated_at FROM progress WHERE learner=? ORDER BY updated_at DESC",(learner,)).fetchall()
    conn.close()
    keys=["learner","item_type","item_id","score","attempts","updated_at"]
    return [dict(zip(keys,r)) for r in rows]

def random_vocab_quiz(language: str="english", count: int=10):
    pool=[e for e in LEXICON if e.get(language)]
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
        result.append({"id":e["transliteration"],"prompt":f"What does '{e['transliteration']}' mean?","choices":choices,"answer":correct,"hieroglyphs":e.get("hieroglyphs","")})
    return result
