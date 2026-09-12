from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .runtime import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_feedback_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS feedback(
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            source_text TEXT NOT NULL DEFAULT '',
            source_language TEXT NOT NULL DEFAULT '',
            target_language TEXT NOT NULL DEFAULT '',
            rating INTEGER NOT NULL DEFAULT 0,
            correction TEXT NOT NULL DEFAULT '',
            context TEXT NOT NULL DEFAULT '',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id, created_at DESC);
        """
    )
    conn.commit()
    conn.close()


def create_feedback(
    user_id: int,
    kind: str,
    source_text: str,
    source_language: str,
    target_language: str,
    rating: int = 0,
    correction: str = "",
    context: str = "",
    note: str = "",
) -> dict:
    if kind not in {"translation", "vision", "dictionary", "lesson", "pronunciation"}:
        raise ValueError("Unsupported feedback kind.")
    if rating not in {-1, 0, 1}:
        raise ValueError("Rating must be -1, 0 or 1.")
    item_id = str(uuid.uuid4())
    now = _now()
    conn = connect()
    conn.execute(
        """
        INSERT INTO feedback(
            id,user_id,kind,source_text,source_language,target_language,rating,correction,context,note,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            item_id,
            user_id,
            kind,
            source_text[:5000],
            source_language[:40],
            target_language[:40],
            rating,
            correction[:5000],
            context[:4000],
            note[:3000],
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM feedback WHERE id=?", (item_id,)).fetchone()
    conn.close()
    return dict(row)


def list_feedback(limit: int = 100, kind: str | None = None) -> list[dict]:
    conn = connect()
    if kind:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE kind=? ORDER BY created_at DESC LIMIT ?",
            (kind, max(1, min(int(limit), 500))),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
