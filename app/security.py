from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import HTTPException, Request, status

_LOCK = threading.Lock()
_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    # Do not trust X-Forwarded-For by default. In multi-instance production,
    # enforce global rate limiting at a trusted reverse proxy or shared store.
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    key = (bucket, client_key(request))
    with _LOCK:
        q = _WINDOWS[key]
        cutoff = now - window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests. Please try again shortly.")
        q.append(now)


def unsafe_origin_allowed(request: Request) -> bool:
    """CSRF hardening for browser-originated unsafe requests.

    API/native clients may omit Origin. When a browser supplies Origin, require the
    same Host unless explicitly whitelisted. This complements SameSite cookies;
    it does not replace reverse-proxy CSRF/rate controls in larger deployments.
    """
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin:
        return True
    parsed = urlparse(origin)
    host = request.headers.get("host", "")
    if parsed.netloc == host:
        return True
    allowed = {
        value.strip().rstrip("/")
        for value in os.environ.get("ESHB_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    }
    return origin in allowed


def enforce_unsafe_origin(request: Request) -> None:
    if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and not unsafe_origin_allowed(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed for state-changing request.")


def security_headers(response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; connect-src 'self'; font-src 'self' data:; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if os.environ.get("ESHB_ENV", "").strip().lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
