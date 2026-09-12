from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

from fastapi import WebSocket, WebSocketDisconnect

from .contextual import contextual_translate
from .vision import analyze_frame


def _allowed_origins() -> set[str]:
    configured = {
        item.strip().rstrip("/")
        for item in os.environ.get("ESHB_ALLOWED_WS_ORIGINS", "").split(",")
        if item.strip()
    }
    return configured


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = (websocket.headers.get("origin") or "").rstrip("/")
    if not origin:
        # Non-browser/native clients may omit Origin. Production operators can
        # require explicit origins via ESHB_WS_REQUIRE_ORIGIN.
        return os.environ.get("ESHB_WS_REQUIRE_ORIGIN", "false").lower() not in {"1", "true", "yes", "on"}
    configured = _allowed_origins()
    if origin in configured:
        return True
    parsed = urlparse(origin)
    host = websocket.headers.get("host", "")
    return bool(parsed.netloc and parsed.netloc == host)


class ConnectionRate:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        self.events: deque[float] = deque()

    def check(self) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        while self.events and self.events[0] < cutoff:
            self.events.popleft()
        if len(self.events) >= self.limit:
            return False
        self.events.append(now)
        return True


async def _accept_or_reject(websocket: WebSocket) -> bool:
    if not _origin_allowed(websocket):
        await websocket.close(code=1008, reason="WebSocket origin not allowed")
        return False
    await websocket.accept()
    return True


async def vision_socket(websocket: WebSocket) -> None:
    if not await _accept_or_reject(websocket):
        return
    rate = ConnectionRate(limit=30)
    sequence = 0
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "error": "Message must be a JSON object."})
                continue
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if message.get("type", "frame") != "frame":
                await websocket.send_json({"type": "error", "error": "Unsupported message type."})
                continue
            if not rate.check():
                await websocket.send_json({"type": "error", "error": "Live vision rate limit reached. Slow the capture cadence.", "retry": True})
                continue
            image = str(message.get("image_data_url") or "")
            if not image:
                await websocket.send_json({"type": "error", "error": "image_data_url is required."})
                continue
            sequence += 1
            try:
                result = await analyze_frame(
                    image,
                    target_language=str(message.get("target_language") or "english"),
                    context=str(message.get("context") or "")[:2000],
                    detail=str(message.get("detail") or "high"),
                )
                await websocket.send_json({"type": "analysis", "sequence": sequence, "result": result})
            except ValueError as exc:
                await websocket.send_json({"type": "error", "sequence": sequence, "error": str(exc)})
            except Exception as exc:
                await websocket.send_json({"type": "error", "sequence": sequence, "error": f"Vision analysis failed: {exc}"})
    except WebSocketDisconnect:
        return


async def conversation_socket(websocket: WebSocket) -> None:
    if not await _accept_or_reject(websocket):
        return
    rate = ConnectionRate(limit=120)
    turn = 0
    conversation_notes: list[str] = []
    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json({"type": "error", "error": "Message must be a JSON object."})
                continue
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if message.get("type", "utterance") == "reset":
                conversation_notes.clear()
                turn = 0
                await websocket.send_json({"type": "reset", "ok": True})
                continue
            if message.get("type", "utterance") != "utterance":
                await websocket.send_json({"type": "error", "error": "Unsupported message type."})
                continue
            if not rate.check():
                await websocket.send_json({"type": "error", "error": "Conversation rate limit reached.", "retry": True})
                continue
            text = str(message.get("text") or "").strip()
            if not text:
                await websocket.send_json({"type": "error", "error": "text is required."})
                continue
            if len(text) > 5000:
                await websocket.send_json({"type": "error", "error": "Utterance exceeds 5000 characters."})
                continue
            source = str(message.get("source") or "english")
            target = str(message.get("target") or "egyptian")
            user_context = str(message.get("context") or "")[:2000]
            inherited = " | ".join(conversation_notes[-4:])
            combined_context = user_context
            if inherited:
                combined_context = f"{user_context}\nRecent conversation: {inherited}".strip()
            turn += 1
            try:
                result = await contextual_translate(
                    text,
                    source,
                    target,
                    context=combined_context[:4000],
                    register=str(message.get("register") or "natural"),
                    use_ai=bool(message.get("use_ai", True)),
                    max_alternatives=min(max(int(message.get("max_alternatives", 4)), 1), 10),
                )
                # Keep only a compact meaning trace in-memory for this socket; no
                # conversation is persisted by the streaming layer.
                preferred = (
                    result.get("ai", {}).get("review", {}).get("preferred_interpretation", {}).get("text")
                    or result.get("deterministic", {}).get("literal_gloss")
                    or result.get("deterministic", {}).get("transliteration")
                    or ""
                )
                conversation_notes.append(f"{source}: {text[:250]} => {target}: {str(preferred)[:250]}")
                await websocket.send_json({"type": "translation", "turn": turn, "result": result})
            except Exception as exc:
                await websocket.send_json({"type": "error", "turn": turn, "error": f"Translation failed: {exc}"})
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return


def streaming_capabilities() -> dict[str, Any]:
    return {
        "vision_websocket": "/ws/vision",
        "conversation_websocket": "/ws/conversation",
        "backpressure": "one request is processed before the next result is emitted on each connection",
        "persistence": "The streaming layer keeps only a short in-memory conversation trace and does not persist frames or turns.",
        "origin_policy": "same-origin by default; additional origins require ESHB_ALLOWED_WS_ORIGINS",
    }
