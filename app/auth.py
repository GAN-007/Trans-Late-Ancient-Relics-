from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Callable

from fastapi import Depends, HTTPException, Request, Response, status

from .config import ROLE_ORDER, VALID_ROLES, settings
from . import storage

PBKDF2_ITERATIONS = 310_000


def hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters long")
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex()


def verify_password(password: str, expected_hash: str, salt_hex: str) -> bool:
    candidate, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, expected_hash)


def public_user(user: dict | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "disabled": bool(user.get("disabled")),
        "created_at": user.get("created_at"),
    }


def bootstrap_admin() -> None:
    if not settings.admin_email or not settings.admin_password:
        return
    existing = storage.get_user_by_email(settings.admin_email)
    if existing:
        if existing["role"] != "admin":
            storage.set_user_role(existing["id"], "admin")
        return
    password_hash, salt = hash_password(settings.admin_password)
    storage.create_user(settings.admin_email, settings.admin_name, password_hash, salt, "admin")


def register_user(email: str, display_name: str, password: str) -> dict:
    if not settings.allow_registration:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    if storage.get_user_by_email(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    try:
        password_hash, salt = hash_password(password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    user = storage.create_user(email, display_name, password_hash, salt, "learner")
    storage.audit("user.register", user["id"], "user", user["id"])
    return user


def authenticate(email: str, password: str) -> dict:
    user = storage.get_user_by_email(email)
    if not user or user.get("disabled") or not verify_password(password, user["password_hash"], user["password_salt"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return user


def start_session(response: Response, user: dict, request: Request) -> str:
    user_agent = request.headers.get("user-agent", "")[:500]
    forwarded = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")
    ip_hint = forwarded.split(",")[0].strip()[:80] if forwarded else None
    token, _ = storage.create_session(user["id"], user_agent, ip_hint)
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    storage.audit("user.login", user["id"], "user", user["id"])
    return token


def end_session(response: Response, request: Request) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    user = storage.get_session_user(token)
    storage.delete_session(token)
    response.delete_cookie(settings.session_cookie_name, path="/")
    if user:
        storage.audit("user.logout", user["id"], "user", user["id"])


def current_user_optional(request: Request) -> dict | None:
    token = request.cookies.get(settings.session_cookie_name)
    return storage.get_session_user(token)


def current_user(request: Request) -> dict:
    user = current_user_optional(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required")
    return user


def require_role(minimum_role: str) -> Callable:
    if minimum_role not in ROLE_ORDER:
        raise RuntimeError(f"Unknown role {minimum_role}")

    def dependency(user: dict = Depends(current_user)) -> dict:
        if ROLE_ORDER.get(user.get("role", "guest"), -1) < ROLE_ORDER[minimum_role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{minimum_role} role required")
        return user

    return dependency


def validate_role(role: str) -> str:
    if role not in VALID_ROLES or role == "guest":
        raise HTTPException(status_code=422, detail=f"Role must be one of {', '.join(r for r in VALID_ROLES if r != 'guest')}")
    return role
