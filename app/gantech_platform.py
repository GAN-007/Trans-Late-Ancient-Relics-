"""GAN-TECH platform client: subscription access checks and enquiry forwarding.

Trans-Late Ancient Relics is part of the GAN-TECH group. The group platform (gan-tech.pro)
holds customer organisations and their subscriptions; this module asks it
whether the person signing in may use this product, and forwards enquiries to
the group inbox.

Opt-in: nothing happens until these environment variables are set (the values
come from ``npm run keys:products`` on the platform):

    GANTECH_API_URL=https://gan-tech.pro/api/v1
    GANTECH_API_KEY=gt_live_...           # access_read + leads_write, limited to this product
    GANTECH_PRODUCT=<product-slug>
    GANTECH_ACCESS_FAIL_MODE=open         # "open" (default): allow sign-in if the platform is unreachable
                                          # "closed": refuse sign-in when access can't be confirmed

Typical use at sign-in::

    from gantech_platform import has_access
    if not has_access(user.email):
        deny("Your organisation doesn't have an active plan for this product.")

Standard library only, so it adds no dependencies.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

__all__ = ["PlatformError", "configured", "check_access", "has_access", "forward_enquiry", "clear_cache"]

_CACHE_SECONDS = 60
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()


class PlatformError(Exception):
    """The platform could not be reached or rejected the request."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _settings() -> tuple[str, str, str]:
    return (
        os.environ.get("GANTECH_API_URL", "").rstrip("/"),
        os.environ.get("GANTECH_API_KEY", ""),
        os.environ.get("GANTECH_PRODUCT", ""),
    )


def configured() -> bool:
    """True when the access check is switched on for this deployment."""
    url, key, product = _settings()
    return bool(url and key and product)


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _request(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    url, key, _ = _settings()
    if not url.startswith(("https://", "http://")):
        raise PlatformError("GANTECH_API_URL must be an http(s) address")
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    # Only http(s) URLs reach this point (checked above).
    request = urllib.request.Request(f"{url}{path}", data=data, method=method, headers=headers)  # noqa: S310  # nosec B310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        try:
            message = json.loads(error.read().decode()).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            message = ""
        raise PlatformError(message or f"GAN-TECH platform returned HTTP {error.code}", error.code) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise PlatformError(f"GAN-TECH platform unreachable: {error}") from error


def check_access(email: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """The platform's answer for this person and product, or None when not configured.

    Returns a dict with ``access`` (bool), ``organization``, ``customer`` and
    ``subscriptions`` (plan, status, seats, trialEndsAt, renewsAt, …).
    Answers are cached for a minute. Raises PlatformError on failure.
    """
    if not configured():
        return None
    _, _, product = _settings()
    normalised = (email or "").strip().lower()
    if "@" not in normalised:
        return {"access": False, "customer": None, "organization": None, "subscriptions": []}
    cache_key = f"{product}:{normalised}"
    now = time.monotonic()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and hit[0] > now:
            return hit[1]
    query = urllib.parse.urlencode({"email": normalised, "product": product})
    data = _request("GET", f"/access?{query}", timeout=timeout).get("data") or {}
    with _lock:
        _cache[cache_key] = (now + _CACHE_SECONDS, data)
    return data


def has_access(email: str) -> bool:
    """Whether to let this person in. Always True when the check isn't configured."""
    if not configured():
        return True
    try:
        result = check_access(email)
    except PlatformError:
        return os.environ.get("GANTECH_ACCESS_FAIL_MODE", "open").lower() != "closed"
    return bool(result and result.get("access"))


def forward_enquiry(
    *,
    name: str,
    email: str,
    message: str,
    enquiry_type: str = "product",
    organisation: str = "",
    phone: str = "",
    timeout: float = 5.0,
) -> dict[str, Any] | None:
    """Sends a contact-form enquiry to the group inbox, tagged with this product.

    Returns the platform's response, or None when not configured. Raises PlatformError on failure.
    """
    if not configured():
        return None
    _, _, product = _settings()
    return _request(
        "POST",
        "/leads",
        {
            "name": name,
            "email": email,
            "message": message,
            "enquiryType": enquiry_type,
            "organisation": organisation,
            "phone": phone,
            "productName": product,
            "consent": True,
        },
        timeout=timeout,
    )
