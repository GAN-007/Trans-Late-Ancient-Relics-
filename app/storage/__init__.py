"""Institutional storage: PostgreSQL, object storage, audit log and model registry.

Single-node installs keep using SQLite and the local disk. Set ESHB_DATABASE_URL to a
postgresql:// URL (and ESHB_OBJECT_STORE=s3) to run several application nodes against shared
storage; app.runtime.connect() then returns a PostgreSQL connection with the same interface.
"""
from __future__ import annotations

import os


def database_url() -> str:
    return os.environ.get("ESHB_DATABASE_URL", "").strip()


def is_postgres() -> bool:
    return database_url().startswith(("postgres://", "postgresql://"))
