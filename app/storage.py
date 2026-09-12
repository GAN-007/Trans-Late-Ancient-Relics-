from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .config import settings


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@contextmanager
def connect():
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'learner',
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions(
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                user_agent TEXT,
                ip_hint TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

            CREATE TABLE IF NOT EXISTS progress(
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, item_type, item_id)
            );

            CREATE TABLE IF NOT EXISTS translation_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                source_text TEXT NOT NULL,
                source_language TEXT NOT NULL,
                target_language TEXT NOT NULL,
                mode TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_history_user_time ON translation_history(user_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS translation_feedback(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                translation_id INTEGER REFERENCES translation_history(id) ON DELETE SET NULL,
                rating TEXT NOT NULL,
                suggested_translation TEXT,
                context TEXT,
                notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unresolved_terms(
                term TEXT NOT NULL,
                source_language TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                last_context TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                PRIMARY KEY(term, source_language)
            );

            CREATE TABLE IF NOT EXISTS lexicon_proposals(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                transliteration TEXT NOT NULL,
                english_json TEXT NOT NULL,
                swahili_json TEXT NOT NULL,
                pos TEXT NOT NULL,
                hieroglyphs TEXT,
                gardiner_json TEXT,
                mdc TEXT,
                notes TEXT,
                evidence TEXT,
                confidence TEXT NOT NULL DEFAULT 'proposed',
                ai_generated INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                review_notes TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_proposals_status ON lexicon_proposals(status, created_at DESC);

            CREATE TABLE IF NOT EXISTS community_lexicon(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER UNIQUE REFERENCES lexicon_proposals(id) ON DELETE SET NULL,
                transliteration TEXT NOT NULL,
                pos TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_community_translit ON community_lexicon(transliteration);

            CREATE TABLE IF NOT EXISTS audit_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(created_at DESC);
            """
        )


def audit(action: str, user_id: int | None = None, entity_type: str | None = None, entity_id: str | int | None = None, metadata: dict | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO audit_events(user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(?,?,?,?,?,?)",
            (user_id, action, entity_type, None if entity_id is None else str(entity_id), json_dumps(metadata or {}), utcnow()),
        )


def create_user(email: str, display_name: str, password_hash: str, password_salt: str, role: str = "learner") -> dict:
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO users(email,display_name,password_hash,password_salt,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (email.lower().strip(), display_name.strip(), password_hash, password_salt, role, now, now),
        )
        user_id = cur.lastrowid
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row)


def get_user_by_email(email: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email.strip(),)).fetchone()
        return dict(row) if row else None


def get_user(user_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_users(limit: int = 200) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,email,display_name,role,disabled,created_at,updated_at FROM users ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def set_user_role(user_id: int, role: str) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE users SET role=?,updated_at=? WHERE id=?", (role, utcnow(), user_id))
    return get_user(user_id)


def set_user_disabled(user_id: int, disabled: bool) -> dict | None:
    with connect() as conn:
        conn.execute("UPDATE users SET disabled=?,updated_at=? WHERE id=?", (1 if disabled else 0, utcnow(), user_id))
        if disabled:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
    return get_user(user_id)


def create_session(user_id: int, user_agent: str | None = None, ip_hint: str | None = None) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.session_days)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token_hash,user_id,created_at,expires_at,user_agent,ip_hint) VALUES(?,?,?,?,?,?)",
            (token_hash, user_id, now.isoformat(), expires.isoformat(), user_agent, ip_hint),
        )
    return token, expires.isoformat()


def get_session_user(token: str | None) -> dict | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    now = utcnow()
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        row = conn.execute(
            """
            SELECT u.* FROM sessions s
            JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>=? AND u.disabled=0
            """,
            (token_hash, now),
        ).fetchone()
        return dict(row) if row else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))


def save_progress(user_id: int, item_type: str, item_id: str, score: float) -> dict:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO progress(user_id,item_type,item_id,score,attempts,updated_at)
            VALUES(?,?,?,?,1,?)
            ON CONFLICT(user_id,item_type,item_id)
            DO UPDATE SET score=excluded.score, attempts=progress.attempts+1, updated_at=excluded.updated_at
            """,
            (user_id, item_type, item_id, float(score), now),
        )
        row = conn.execute(
            "SELECT item_type,item_id,score,attempts,updated_at FROM progress WHERE user_id=? AND item_type=? AND item_id=?",
            (user_id, item_type, item_id),
        ).fetchone()
        return dict(row)


def get_progress(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT item_type,item_id,score,attempts,updated_at FROM progress WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_translation(user_id: int | None, source_text: str, source_language: str, target_language: str, mode: str, result: dict) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO translation_history(user_id,source_text,source_language,target_language,mode,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, source_text, source_language, target_language, mode, json_dumps(result), utcnow()),
        )
        return int(cur.lastrowid)


def translation_history(user_id: int, limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,source_text,source_language,target_language,mode,result_json,created_at FROM translation_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [{**dict(r), "result": json_loads(r["result_json"], {})} for r in rows]


def add_feedback(user_id: int | None, translation_id: int | None, rating: str, suggested_translation: str | None, context: str | None, notes: str | None) -> dict:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO translation_feedback(user_id,translation_id,rating,suggested_translation,context,notes,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, translation_id, rating, suggested_translation, context, notes, utcnow()),
        )
        row = conn.execute("SELECT * FROM translation_feedback WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def record_unresolved(term: str, source_language: str, context: str | None = None) -> None:
    term = term.strip().lower()
    if not term:
        return
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO unresolved_terms(term,source_language,count,last_context,first_seen,last_seen)
            VALUES(?,?,1,?,?,?)
            ON CONFLICT(term,source_language)
            DO UPDATE SET count=unresolved_terms.count+1,last_context=excluded.last_context,last_seen=excluded.last_seen
            """,
            (term, source_language, context, now, now),
        )


def learning_insights(limit: int = 100) -> dict:
    with connect() as conn:
        unresolved = [dict(r) for r in conn.execute(
            "SELECT * FROM unresolved_terms ORDER BY count DESC,last_seen DESC LIMIT ?", (limit,)
        ).fetchall()]
        feedback = [dict(r) for r in conn.execute(
            "SELECT rating,COUNT(*) AS count FROM translation_feedback GROUP BY rating ORDER BY count DESC"
        ).fetchall()]
        proposals = [dict(r) for r in conn.execute(
            "SELECT status,COUNT(*) AS count FROM lexicon_proposals GROUP BY status ORDER BY count DESC"
        ).fetchall()]
    return {"unresolved_terms": unresolved, "feedback_summary": feedback, "proposal_summary": proposals}


def create_proposal(user_id: int | None, payload: dict, ai_generated: bool = False) -> dict:
    now = utcnow()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO lexicon_proposals(
                user_id,transliteration,english_json,swahili_json,pos,hieroglyphs,gardiner_json,mdc,
                notes,evidence,confidence,ai_generated,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'pending', ?)
            """,
            (
                user_id,
                payload["transliteration"].strip(),
                json_dumps(payload.get("english", [])),
                json_dumps(payload.get("swahili", [])),
                payload.get("pos", "unknown").strip(),
                payload.get("hieroglyphs"),
                json_dumps(payload.get("gardiner", [])),
                payload.get("mdc"),
                payload.get("notes"),
                payload.get("evidence"),
                payload.get("confidence", "proposed"),
                1 if ai_generated else 0,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM lexicon_proposals WHERE id=?", (cur.lastrowid,)).fetchone()
    return proposal_row(dict(row))


def proposal_row(row: dict) -> dict:
    row = dict(row)
    row["english"] = json_loads(row.pop("english_json", "[]"), [])
    row["swahili"] = json_loads(row.pop("swahili_json", "[]"), [])
    row["gardiner"] = json_loads(row.pop("gardiner_json", "[]"), [])
    row["ai_generated"] = bool(row.get("ai_generated"))
    return row


def list_proposals(status: str | None = None, limit: int = 200) -> list[dict]:
    with connect() as conn:
        if status:
            rows = conn.execute("SELECT * FROM lexicon_proposals WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM lexicon_proposals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [proposal_row(dict(r)) for r in rows]


def review_proposal(proposal_id: int, reviewer_id: int, decision: str, notes: str | None = None) -> dict | None:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    with connect() as conn:
        row = conn.execute("SELECT * FROM lexicon_proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            return None
        if row["status"] != "pending":
            return proposal_row(dict(row))
        now = utcnow()
        conn.execute(
            "UPDATE lexicon_proposals SET status=?,reviewer_id=?,review_notes=?,reviewed_at=? WHERE id=?",
            (decision, reviewer_id, notes, now, proposal_id),
        )
        if decision == "approved":
            entry = {
                "transliteration": row["transliteration"],
                "english": json_loads(row["english_json"], []),
                "swahili": json_loads(row["swahili_json"], []),
                "pos": row["pos"],
                "hieroglyphs": row["hieroglyphs"],
                "gardiner": json_loads(row["gardiner_json"], []),
                "mdc": row["mdc"],
                "notes": row["notes"],
                "confidence": "reviewed",
                "provenance": {"type": "community_reviewed", "proposal_id": proposal_id},
            }
            conn.execute(
                "INSERT OR REPLACE INTO community_lexicon(proposal_id,transliteration,pos,entry_json,approved_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (proposal_id, row["transliteration"], row["pos"], json_dumps(entry), reviewer_id, now, now),
            )
        updated = conn.execute("SELECT * FROM lexicon_proposals WHERE id=?", (proposal_id,)).fetchone()
    return proposal_row(dict(updated))


def approved_lexicon_entries() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT entry_json FROM community_lexicon ORDER BY id ASC").fetchall()
    return [json_loads(r["entry_json"], {}) for r in rows]


def list_audit_events(limit: int = 200) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "metadata": json_loads(r["metadata_json"], {})} for r in rows]
