from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request, status

_LOCK = threading.Lock()
_WINDOWS: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def client_key(request: Request) -> str:
    # Do not trust forwarded headers by default. Deployments can terminate rate limiting at a reverse proxy.
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


def security_headers(response) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; connect-src 'self'; font-src 'self' data:; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
