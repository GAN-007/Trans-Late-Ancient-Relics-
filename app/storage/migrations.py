"""Versioned schema migrations, recorded in schema_migrations, applied at startup on SQLite or PostgreSQL."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ..runtime import connect


def _m001_storage(conn) -> None:
    from . import audit, objects, registry
    for ddl in (objects.SCHEMA, audit.SCHEMA, registry.SCHEMA):
        conn.execute(ddl)


def _m002_corpus(conn) -> None:
    from ..corpus.store import SCHEMA
    for ddl in SCHEMA:
        conn.execute(ddl)


MIGRATIONS: list[tuple[int, str, Callable]] = [
    (1, "object store, audit log, model registry", _m001_storage),
    (2, "attestation corpus (lemmas, senses, texts, objects, attestations)", _m002_corpus),
]


def migrate() -> list[int]:
    conn = connect()
    applied: list[int] = []
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
        conn.commit()
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for version, name, fn in MIGRATIONS:
            if version in done:
                continue
            fn(conn)
            conn.execute("INSERT INTO schema_migrations (version,name,applied_at) VALUES (?,?,?) ON CONFLICT (version) DO NOTHING",
                         (version, name, datetime.now(timezone.utc).isoformat(timespec="seconds")))
            conn.commit()
            applied.append(version)
    finally:
        conn.close()
    return applied


def status() -> list[dict]:
    conn = connect()
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
        conn.commit()
        done = {r["version"]: r["applied_at"] for r in conn.execute("SELECT version, applied_at FROM schema_migrations").fetchall()}
        return [{"version": v, "name": name, "applied": v in done, "applied_at": done.get(v)} for v, name, _ in MIGRATIONS]
    finally:
        conn.close()
