"""Shared test setup: when ESHB_DATABASE_URL points at PostgreSQL, give every test its own schema."""
from __future__ import annotations

import os
import uuid

import pytest


@pytest.fixture(autouse=True)
def _postgres_schema_per_test(monkeypatch):
    url = os.environ.get("ESHB_DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        yield
        return
    schema = f"t_{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("ESHB_DATABASE_SCHEMA", schema)
    yield
    import psycopg
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
