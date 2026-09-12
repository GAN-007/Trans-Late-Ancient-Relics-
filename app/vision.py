from __future__ import annotations

import base64
import binascii
import hashlib
import re
from typing import Any

from .ai import ai_status, analyze_relic_image

DATA_URL_RE = re.compile(r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\r\n]+)$", re.I)
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def validate_image_data_url(data_url: str) -> dict[str, Any]:
    match = DATA_URL_RE.match(data_url.strip())
    if not match:
        raise ValueError("Image must be a PNG, JPEG or WebP data URL.")
    mime = match.group(1).lower()
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Invalid base64 image data.") from exc
    if not raw:
        raise ValueError("Image is empty.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds the {MAX_IMAGE_BYTES // (1024*1024)} MB limit.")
    # Lightweight signature checks prevent arbitrary data from being relayed as an image.
    valid = False
    if mime == "image/png" and raw.startswith(b"\x89PNG\r\n\x1a\n"):
        valid = True
    elif mime == "image/jpeg" and raw.startswith(b"\xff\xd8"):
        valid = True
    elif mime == "image/webp" and len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        valid = True
    if not valid:
        raise ValueError("Image bytes do not match the declared image type.")
    return {"mime": mime, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


async def analyze_frame(data_url: str, target_language: str = "english", context: str = "", detail: str = "high") -> dict[str, Any]:
    metadata = validate_image_data_url(data_url)
    status = ai_status()
    if not status["configured"]:
        return {
            "ok": False,
            "image": metadata,
            "ai": status,
            "message": "Camera capture works, but vision translation requires a configured multimodal AI provider.",
            "privacy": "The server validated the frame and did not persist it.",
        }
    analysis = await analyze_relic_image(data_url, target_language, context=context, detail=detail)
    return {
        "ok": True,
        "image": metadata,
        "ai": status,
        "analysis": analysis,
        "privacy": "The application does not persist the frame. A configured AI provider receives it for analysis.",
    }
