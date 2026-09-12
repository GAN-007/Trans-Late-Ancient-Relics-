from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import HTTPException, Request, Response, status

from .runtime import connect, env_bool

ROLES = ("learner", "contributor", "reviewer", "admin")
ROLE_RANK = {role: index for index, role in enumerate(ROLES)}
PERMISSIONS = {
    "learner": {"progress:write", "history:write", "feedback:create"},
    "contributor": {"progress:write", "history:write", "feedback:create", "proposal:create"},
    "reviewer": {"progress:write", "history:write", "feedback:create", "proposal:create", "proposal:review", "knowledge:inspect"},
    "admin": {"progress:write", "history:write", "feedback:create", "proposal:create", "proposal:review", "knowledge:inspect", "users:manage", "knowledge:run_ai"},
}
SESSION_COOKIE = "eshb_session"
SESSION_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def init_auth_db() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'learner',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        """
    )
    conn.commit()
    conn.close()
    ensure_bootstrap_admin()


def _password_hash(password: str, salt: bytes | None = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    # stdlib scrypt gives us a memory-hard password KDF without another runtime dependency.
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(derived.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _public_user(row: sqlite3.Row | dict) -> dict:
    return {
        "id": int(row["id"]),
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "is_active": bool(row["is_active"]),
        "permissions": sorted(PERMISSIONS.get(row["role"], set())),
    }


def create_user(username: str, password: str, display_name: str | None = None, role: str = "learner") -> dict:
    username = username.strip()
    display_name = (display_name or username).strip()
    if not 3 <= len(username) <= 40 or not all(c.isalnum() or c in "._-" for c in username):
        raise ValueError("Username must be 3-40 characters using letters, numbers, dot, underscore or hyphen.")
    if len(password) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    if role not in ROLES:
        raise ValueError("Invalid role.")
    now = _iso(_now())
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO users(username,display_name,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,1,?,?)",
            (username, display_name, _password_hash(password), role, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        return _public_user(row)
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username is already registered.") from exc
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    conn = connect()
    row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username.strip(),)).fetchone()
    conn.close()
    if not row or not row["is_active"] or not _verify_password(password, row["password_hash"]):
        return None
    return _public_user(row)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = _now()
    conn = connect()
    conn.execute(
        "INSERT INTO sessions(user_id,token_hash,created_at,expires_at,last_seen_at) VALUES(?,?,?,?,?)",
        (user_id, token_hash, _iso(now), _iso(now + timedelta(days=SESSION_DAYS)), _iso(now)),
    )
    conn.commit()
    conn.close()
    return token


def destroy_session(token: str | None) -> None:
    if not token:
        return
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    conn = connect()
    conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
    conn.commit()
    conn.close()


def user_from_session(token: str | None) -> dict | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = _iso(_now())
    conn = connect()
    row = conn.execute(
        """
        SELECT u.* FROM sessions s
        JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1
        """,
        (token_hash, now),
    ).fetchone()
    if row:
        conn.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, token_hash))
        conn.commit()
    else:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        conn.commit()
    conn.close()
    return _public_user(row) if row else None


def get_current_user(request: Request) -> dict | None:
    return user_from_session(request.cookies.get(SESSION_COOKIE))


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    return user


def require_permission(permission: str) -> Callable[[Request], dict]:
    def dependency(request: Request) -> dict:
        user = require_user(request)
        if permission not in PERMISSIONS.get(user["role"], set()):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission required: {permission}")
        return user
    return dependency


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=env_bool("ESHB_SECURE_COOKIES", default=os.environ.get("ESHB_ENV") == "production"),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="lax")


def list_users() -> list[dict]:
    conn = connect()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
    conn.close()
    return [_public_user(row) for row in rows]


def set_user_role(user_id: int, role: str) -> dict:
    if role not in ROLES:
        raise ValueError("Invalid role.")
    conn = connect()
    conn.execute("UPDATE users SET role=?, updated_at=? WHERE id=?", (role, _iso(_now()), user_id))
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        raise ValueError("User not found.")
    return _public_user(row)


def ensure_bootstrap_admin() -> None:
    username = os.environ.get("ESHB_BOOTSTRAP_ADMIN_USERNAME", "").strip()
    password = os.environ.get("ESHB_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username or not password:
        return
    conn = connect()
    row = conn.execute("SELECT id,role FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    conn.close()
    if row:
        if row["role"] != "admin":
            set_user_role(int(row["id"]), "admin")
        return
    try:
        create_user(username, password, os.environ.get("ESHB_BOOTSTRAP_ADMIN_DISPLAY_NAME", "Administrator"), role="admin")
    except ValueError:
        # Startup should remain available even if a stale/malformed bootstrap value is supplied.
        return
