from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .runtime import connect

VALID_KINDS = {"lexicon", "translation", "sign", "pronunciation", "grammar"}
VALID_STATUSES = {"pending", "approved", "rejected"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_knowledge_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_proposals(
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            evidence TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            origin TEXT NOT NULL DEFAULT 'human',
            proposer_user_id INTEGER,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            reviewed_by_user_id INTEGER,
            review_note TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge_proposals(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_knowledge_kind ON knowledge_proposals(kind, status);

        CREATE TABLE IF NOT EXISTS unresolved_terms(
            source_language TEXT NOT NULL,
            term TEXT NOT NULL,
            example_context TEXT NOT NULL DEFAULT '',
            occurrences INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT NOT NULL,
            ai_proposed_at TEXT,
            PRIMARY KEY(source_language, term)
        );

        CREATE TABLE IF NOT EXISTS system_state(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def _row_to_proposal(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "payload": json.loads(row["payload_json"]),
        "evidence": row["evidence"],
        "source_url": row["source_url"],
        "origin": row["origin"],
        "proposer_user_id": row["proposer_user_id"],
        "confidence": row["confidence"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "reviewed_by_user_id": row["reviewed_by_user_id"],
        "review_note": row["review_note"],
        "reviewed_at": row["reviewed_at"],
    }


def _validate_lexicon_payload(payload: dict[str, Any]) -> None:
    required = {"transliteration", "english", "swahili", "pos", "notes", "confidence"}
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"Lexicon proposal is missing fields: {', '.join(sorted(missing))}")
    if not isinstance(payload["english"], list) or not payload["english"]:
        raise ValueError("Lexicon proposal requires at least one English gloss.")
    if not isinstance(payload["swahili"], list) or not payload["swahili"]:
        raise ValueError("Lexicon proposal requires at least one Swahili gloss.")
    if payload["confidence"] not in {"low", "medium", "high"}:
        raise ValueError("Lexicon confidence must be low, medium or high.")


def create_proposal(
    kind: str,
    payload: dict[str, Any],
    evidence: str = "",
    source_url: str = "",
    proposer_user_id: int | None = None,
    origin: str = "human",
    confidence: float | None = None,
) -> dict[str, Any]:
    if kind not in VALID_KINDS:
        raise ValueError("Unsupported proposal kind.")
    if kind == "lexicon":
        _validate_lexicon_payload(payload)
    proposal_id = str(uuid.uuid4())
    now = _now()
    conn = connect()
    conn.execute(
        """
        INSERT INTO knowledge_proposals(
            id,kind,payload_json,evidence,source_url,origin,proposer_user_id,confidence,status,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?, 'pending', ?,?)
        """,
        (
            proposal_id,
            kind,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            evidence.strip(),
            source_url.strip(),
            origin,
            proposer_user_id,
            confidence,
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM knowledge_proposals WHERE id=?", (proposal_id,)).fetchone()
    conn.close()
    return _row_to_proposal(row)


def list_proposals(status: str | None = None, kind: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        if status not in VALID_STATUSES:
            raise ValueError("Invalid status.")
        clauses.append("status=?")
        params.append(status)
    if kind:
        if kind not in VALID_KINDS:
            raise ValueError("Invalid kind.")
        clauses.append("kind=?")
        params.append(kind)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    conn = connect()
    rows = conn.execute(
        f"SELECT * FROM knowledge_proposals{where} ORDER BY created_at DESC LIMIT ?",
        (*params, max(1, min(int(limit), 500))),
    ).fetchall()
    conn.close()
    return [_row_to_proposal(row) for row in rows]


def update_proposal_evidence(proposal_id: str, evidence: str, source_url: str, editor_user_id: int) -> dict[str, Any]:
    conn = connect()
    row = conn.execute("SELECT * FROM knowledge_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("Proposal not found.")
    if row["status"] != "pending":
        conn.close()
        raise ValueError("Only pending proposals can be edited.")
    now = _now()
    conn.execute(
        "UPDATE knowledge_proposals SET evidence=?,source_url=?,updated_at=? WHERE id=?",
        (evidence.strip(), source_url.strip(), now, proposal_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM knowledge_proposals WHERE id=?", (proposal_id,)).fetchone()
    conn.close()
    return _row_to_proposal(row)


def review_proposal(proposal_id: str, status: str, reviewer_user_id: int, note: str = "") -> dict[str, Any]:
    if status not in {"approved", "rejected"}:
        raise ValueError("Review status must be approved or rejected.")
    now = _now()
    conn = connect()
    row = conn.execute("SELECT * FROM knowledge_proposals WHERE id=?", (proposal_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError("Proposal not found.")
    if status == "approved" and row["kind"] == "lexicon":
        evidence = (row["evidence"] or "").strip()
        source_url = (row["source_url"] or "").strip()
        if not evidence and not source_url:
            conn.close()
            raise ValueError("Lexicon approval requires evidence or a source URL.")
        if row["origin"] == "ai" and not source_url:
            conn.close()
            raise ValueError("AI-drafted lexicon entries require a reviewer-supplied source URL before approval.")
        if not note.strip():
            conn.close()
            raise ValueError("Lexicon approval requires a reviewer note.")
    conn.execute(
        """
        UPDATE knowledge_proposals
        SET status=?, reviewed_by_user_id=?, review_note=?, reviewed_at=?, updated_at=?
        WHERE id=?
        """,
        (status, reviewer_user_id, note.strip(), now, now, proposal_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM knowledge_proposals WHERE id=?", (proposal_id,)).fetchone()
    conn.close()
    return _row_to_proposal(row)


def approved_lexicon_entries() -> list[dict[str, Any]]:
    conn = connect()
    rows = conn.execute(
        "SELECT payload_json FROM knowledge_proposals WHERE kind='lexicon' AND status='approved' ORDER BY reviewed_at ASC"
    ).fetchall()
    conn.close()
    entries: list[dict[str, Any]] = []
    for row in rows:
        try:
            entry = json.loads(row["payload_json"])
            _validate_lexicon_payload(entry)
            entry = dict(entry)
            entry["runtime_overlay"] = True
            entries.append(entry)
        except (ValueError, json.JSONDecodeError, TypeError):
            continue
    return entries


def record_unresolved(term: str, source_language: str, example_context: str = "") -> None:
    term = term.strip().lower()
    if not term or len(term) > 120:
        return
    now = _now()
    conn = connect()
    conn.execute(
        """
        INSERT INTO unresolved_terms(source_language,term,example_context,occurrences,last_seen_at)
        VALUES(?,?,?,1,?)
        ON CONFLICT(source_language,term)
        DO UPDATE SET occurrences=unresolved_terms.occurrences+1,
                      example_context=CASE WHEN excluded.example_context<>'' THEN excluded.example_context ELSE unresolved_terms.example_context END,
                      last_seen_at=excluded.last_seen_at
        """,
        (source_language, term, example_context[:1000], now),
    )
    conn.commit()
    conn.close()


def top_unresolved(limit: int = 20, only_without_ai_proposal: bool = False) -> list[dict[str, Any]]:
    where = "WHERE ai_proposed_at IS NULL" if only_without_ai_proposal else ""
    conn = connect()
    rows = conn.execute(
        f"SELECT source_language,term,example_context,occurrences,last_seen_at,ai_proposed_at FROM unresolved_terms {where} ORDER BY occurrences DESC,last_seen_at DESC LIMIT ?",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def mark_ai_proposed(source_language: str, term: str) -> None:
    conn = connect()
    conn.execute(
        "UPDATE unresolved_terms SET ai_proposed_at=? WHERE source_language=? AND term=?",
        (_now(), source_language, term),
    )
    conn.commit()
    conn.close()


def get_state(key: str) -> str | None:
    conn = connect()
    row = conn.execute("SELECT value FROM system_state WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_state(key: str, value: str) -> None:
    now = _now()
    conn = connect()
    conn.execute(
        """
        INSERT INTO system_state(key,value,updated_at) VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at
        """,
        (key, value, now),
    )
    conn.commit()
    conn.close()
