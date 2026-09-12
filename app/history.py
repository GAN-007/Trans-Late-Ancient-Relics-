from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .runtime import connect


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_history_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS translation_history(
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_language TEXT NOT NULL,
            target_language TEXT NOT NULL,
            source_text TEXT NOT NULL,
            result_json TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'text',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_history_user_created ON translation_history(user_id, created_at DESC);
        """
    )
    conn.commit()
    conn.close()


def save_history(user_id: int, source_language: str, target_language: str, source_text: str, result: dict[str, Any], mode: str = "text") -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    now = _now()
    conn = connect()
    conn.execute(
        "INSERT INTO translation_history(id,user_id,source_language,target_language,source_text,result_json,mode,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (item_id, user_id, source_language, target_language, source_text[:5000], json.dumps(result, ensure_ascii=False), mode, now),
    )
    conn.commit()
    conn.close()
    return {"id": item_id, "created_at": now}


def list_history(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM translation_history WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, max(1, min(int(limit), 200))),
    ).fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "source_language": row["source_language"],
            "target_language": row["target_language"],
            "source_text": row["source_text"],
            "result": json.loads(row["result_json"]),
            "mode": row["mode"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def clear_history(user_id: int) -> int:
    conn = connect()
    cur = conn.execute("DELETE FROM translation_history WHERE user_id=?", (user_id,))
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count
