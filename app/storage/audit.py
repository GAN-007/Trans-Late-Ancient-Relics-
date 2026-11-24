"""Tamper-evident audit log.

Each entry stores the SHA-256 of the previous entry, so editing or deleting any past record breaks
the chain and verify() reports where. Appends are serialized (PostgreSQL advisory lock, SQLite
BEGIN IMMEDIATE), so several application nodes can write to one log safely.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..runtime import connect
from . import is_postgres

SCHEMA = """CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, target TEXT, details TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE)"""
GENESIS = "0" * 64
LOCK_ID = 7_413_221


def _digest(prev: str, at: str, actor: str, action: str, target: str | None, details: str) -> str:
    payload = json.dumps([prev, at, actor, action, target, details], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_schema() -> None:
    conn = connect()
    try:
        conn.execute(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def record(actor: str, action: str, target: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    ensure_schema()
    at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    body = json.dumps(details or {}, ensure_ascii=False, sort_keys=True, default=str)
    conn = connect()
    try:
        if is_postgres():
            conn.execute("SELECT pg_advisory_xact_lock(?)", (LOCK_ID,))
        else:
            conn.execute("BEGIN IMMEDIATE")
        last = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = last["hash"] if last else GENESIS
        digest = _digest(prev, at, actor, action, target, body)
        conn.execute("INSERT INTO audit_log (at,actor,action,target,details,prev_hash,hash) VALUES (?,?,?,?,?,?,?)",
                     (at, actor, action, target, body, prev, digest))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"at": at, "actor": actor, "action": action, "target": target, "hash": digest}


def entries(limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
    ensure_schema()
    conn = connect()
    try:
        sql = "SELECT * FROM audit_log" + (" WHERE action=?" if action else "") + " ORDER BY id DESC LIMIT ?"
        rows = conn.execute(sql, ((action, limit) if action else (limit,))).fetchall()
    finally:
        conn.close()
    return [{**dict(r), "details": json.loads(r["details"] or "{}")} for r in rows]


def verify() -> dict[str, Any]:
    """Recompute the chain; any edited, inserted or deleted record shows up as a break."""
    ensure_schema()
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    finally:
        conn.close()
    prev = GENESIS
    for row in rows:
        expected = _digest(prev, row["at"], row["actor"], row["action"], row["target"], row["details"])
        if row["prev_hash"] != prev or row["hash"] != expected:
            return {"ok": False, "entries": len(rows), "broken_at": row["id"],
                    "reason": "previous-hash link broken" if row["prev_hash"] != prev else "record content changed"}
        prev = row["hash"]
    return {"ok": True, "entries": len(rows), "head": prev}
