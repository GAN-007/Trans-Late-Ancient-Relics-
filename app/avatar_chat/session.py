"""Live avatar chat session over WebSocket.

Implements the text and control subset of OpenAvatarChat's session protocol
(src/handlers/client/ws_client/ws_message_protocol.py): every message is
{"header": {"name", "request_id"}, "payload": {...}}, with the same names
(InitializeAvatarSession, SendHumanText, Interrupt, TriggerHeartbeat, EndSpeech
/ AvatarSessionInitialized, EchoHumanText, EchoAvatarText, InterruptAccepted,
AvatarHeartbeat, ChatSignal, Error).

Additions for a browser-rendered avatar: AvatarSpeech (one sentence to speak
plus its ARKit motion track), AvatarCard (verified translation table),
UpdateContext and SetPersona.

Stream lifecycle follows OAC's StreamManager: each human turn opens a stream,
the reply opens a child stream, and an interrupt or a new human turn cancels
the reply chain. Cancelled replies are not written to history, as in OAC.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ..streaming import ConnectionRate, _origin_allowed
from .brain import BrainContext, llm_status, think
from .personas import PERSONAS, get_persona
from .text_tools import SentenceBuffer, speakable
from .visemes import motion_track

MAX_MESSAGE_BYTES = 16_000
MAX_HUMAN_TEXT = 2_000
CLIENT_MESSAGES = {"InitializeAvatarSession", "SendHumanText", "Interrupt", "TriggerHeartbeat", "EndSpeech", "UpdateContext", "SetPersona"}


def _limit(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


class _SessionCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0

    def acquire(self, limit: int) -> bool:
        with self._lock:
            if self.active >= limit:
                return False
            self.active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self.active = max(0, self.active - 1)


SESSIONS = _SessionCounter()


@dataclass
class Stream:
    key: str
    kind: str  # human_text | avatar_text | client_playback
    parent: str | None = None
    status: str = "started"  # started | ended | cancelled


@dataclass
class AvatarSession:
    websocket: WebSocket
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    brain: BrainContext | None = None
    streams: dict[str, Stream] = field(default_factory=dict)
    counter: int = 0
    reply_task: asyncio.Task | None = None
    reply_stream: str | None = None
    pending_human: dict[str, str] = field(default_factory=dict)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    started: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    initialized: bool = False

    # ------------------------------------------------------------ sending
    async def send(self, name: str, payload: dict[str, Any] | None = None, request_id: str | None = None) -> None:
        message: dict[str, Any] = {"header": {"name": name, "request_id": request_id or uuid.uuid4().hex[:12]}}
        if payload is not None:
            message["payload"] = payload
        async with self.send_lock:
            await self.websocket.send_text(json.dumps(message, ensure_ascii=False))

    async def error(self, code: str, message: str, request_id: str | None = None) -> None:
        await self.send("Error", {"code": code, "message": message}, request_id)

    async def signal(self, kind: str, stream: Stream, data: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"timestamp": time.time(), "type": kind, "source_type": "handler",
                                   "stream_type": stream.kind, "stream_producer": "avatar_chat", "stream_key": stream.key}
        if kind == "stream_begin" and stream.parent:
            payload["parent_stream_keys"] = [stream.parent]
        if data:
            payload["signal_data"] = data
        await self.send("ChatSignal", payload)

    # ------------------------------------------------------------ streams
    def new_stream(self, kind: str, parent: str | None = None, key: str | None = None) -> Stream:
        self.counter += 1
        stream = Stream(key or f"stream_avatar_{self.counter}", kind, parent)
        self.streams[stream.key] = stream
        if len(self.streams) > 200:  # recycle finished streams
            for old in [k for k, s in self.streams.items() if s.status != "started"][:100]:
                self.streams.pop(old, None)
        return stream

    async def cancel_reply(self, reason: str) -> str | None:
        key = self.reply_stream
        task = self.reply_task
        if not key or not task or task.done():
            return None
        stream = self.streams.get(key)
        if stream:
            stream.status = "cancelled"
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        self.reply_task = None
        self.reply_stream = None
        if stream:
            await self.signal("stream_cancel", stream, {"reason": reason})
        return key

    # ------------------------------------------------------------ handlers
    async def on_initialize(self, payload: dict[str, Any], request_id: str) -> None:
        persona = get_persona(payload.get("persona"))
        self.brain = BrainContext(persona=persona, max_history=_limit("ESHB_AVATAR_HISTORY_TURNS", 20))
        self.brain.environment = _clean_context(payload.get("context"))
        self.initialized = True
        status = llm_status()
        await self.send("AvatarSessionInitialized", {
            "session_id": self.session_id,
            "persona": persona.public(),
            "personas": [p.public() for p in PERSONAS.values()],
            "llm": {"configured": status["configured"], "model": status["model"], "api": status["api"]},
            "limits": {"heartbeat_timeout": _limit("ESHB_AVATAR_HEARTBEAT_TIMEOUT", 30),
                       "connection_ttl": _limit("ESHB_AVATAR_CONNECTION_TTL", 900), "max_text": MAX_HUMAN_TEXT},
        }, request_id)
        await self.speak_greeting()

    async def speak_greeting(self) -> None:
        assert self.brain
        stream = self.new_stream("avatar_text")
        await self.signal("stream_begin", stream)
        text = self.brain.persona.greeting
        await self.send("EchoAvatarText", {"stream_key": stream.key, "mode": "full_text", "text": text, "end_of_speech": True})
        await self.send_speech(stream.key, 0, text, final=True)
        stream.status = "ended"
        await self.signal("stream_end", stream)

    async def send_speech(self, stream_key: str, index: int, sentence: str, final: bool) -> None:
        assert self.brain
        spoken = speakable(sentence)
        if not spoken:
            if final:
                await self.send("AvatarSpeech", {"stream_key": stream_key, "index": index, "text": "", "end_of_speech": True})
            return
        persona = self.brain.persona
        await self.send("AvatarSpeech", {
            "stream_key": stream_key, "index": index, "text": spoken, "end_of_speech": final,
            "voice": {"lang": persona.voice_lang, "rate": persona.voice_rate, "pitch": persona.voice_pitch},
            "motion": motion_track(spoken, persona.voice_rate),
        })

    async def on_human_text(self, payload: dict[str, Any], request_id: str) -> None:
        if not self.brain:
            return await self.error("INVALID_SESSION", "Send InitializeAvatarSession first.", request_id)
        text = str(payload.get("text") or "")
        key = str(payload.get("stream_key") or f"stream_client_{uuid.uuid4().hex[:8]}")[:80]
        if payload.get("mode", "increment") == "full_text":
            self.pending_human[key] = text
        else:
            self.pending_human[key] = self.pending_human.get(key, "") + text
        if len(self.pending_human[key]) > MAX_HUMAN_TEXT:
            self.pending_human.pop(key, None)
            return await self.error("INVALID_MESSAGE", f"Message exceeds {MAX_HUMAN_TEXT} characters.", request_id)
        if not payload.get("end_of_speech", True):
            return
        full = self.pending_human.pop(key, "").strip()
        if not full:
            return
        if not self.rate.check():
            return await self.error("RATE_LIMIT", "You're sending messages very quickly. Give me a moment.", request_id)
        interrupted = await self.cancel_reply("new_human_turn")
        if interrupted:
            await self.send("InterruptNotification", {"target_stream_id": interrupted, "stream_key": interrupted, "reason": "user_interrupt", "interrupted_at": time.time()})
        human = self.new_stream("human_text", key=key if key not in self.streams else None)
        human.status = "ended"
        await self.send("EchoHumanText", {"stream_key": human.key, "mode": "full_text", "text": full, "end_of_speech": True}, request_id)
        reply = self.new_stream("avatar_text", parent=human.key)
        self.reply_stream = reply.key
        self.reply_task = asyncio.create_task(self.generate(full, reply))

    async def generate(self, user_text: str, stream: Stream) -> None:
        assert self.brain
        await self.signal("stream_begin", stream)
        buffer = SentenceBuffer(split_on_clause=False)
        spoken_index = 0
        reply_text = ""
        try:
            async for event in think(self.brain, user_text, self.transport):
                if stream.status == "cancelled":
                    return
                if event["type"] == "card":
                    await self.send("AvatarCard", {"stream_key": stream.key, "card": event["card"]})
                elif event["type"] == "notice":
                    await self.send("AvatarNotice", {"stream_key": stream.key, "text": event["text"]})
                elif event["type"] == "delta":
                    reply_text += event["text"]
                    await self.send("EchoAvatarText", {"stream_key": stream.key, "mode": "increment", "text": event["text"], "end_of_speech": False})
                    for sentence in buffer.process(event["text"]):
                        await self.send_speech(stream.key, spoken_index, sentence, final=False)
                        spoken_index += 1
            rest = buffer.flush()
            for i, sentence in enumerate(rest):
                await self.send_speech(stream.key, spoken_index, sentence, final=i == len(rest) - 1)
                spoken_index += 1
            if not rest:
                await self.send("AvatarSpeech", {"stream_key": stream.key, "index": spoken_index, "text": "", "end_of_speech": True})
            await self.send("EchoAvatarText", {"stream_key": stream.key, "mode": "increment", "text": "", "end_of_speech": True})
            stream.status = "ended"
            await self.signal("stream_end", stream)
            self.brain.remember("user", user_text)
            self.brain.remember("assistant", reply_text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # never leave the client waiting on a half-open stream
            stream.status = "ended"
            await self.error("INTERNAL_ERROR", f"Reply failed: {exc}")
            await self.send("EchoAvatarText", {"stream_key": stream.key, "mode": "increment", "text": "", "end_of_speech": True})
            await self.signal("stream_end", stream, {"error": True})
        finally:
            if self.reply_stream == stream.key:
                self.reply_stream = None

    async def on_interrupt(self, request_id: str) -> None:
        key = await self.cancel_reply("user_interrupt")
        await self.send("InterruptAccepted", {"target_stream_id": key, "stream_key": key} if key else {}, request_id)

    async def on_end_speech(self, payload: dict[str, Any]) -> None:
        key = str(payload.get("stream_key") or "")
        if key in self.streams:
            playback = self.new_stream("client_playback", parent=key)
            playback.status = "ended"
            await self.signal("stream_end", playback)

    async def on_update_context(self, payload: dict[str, Any]) -> None:
        if self.brain:
            self.brain.environment.update(_clean_context(payload))

    async def on_set_persona(self, payload: dict[str, Any], request_id: str) -> None:
        if not self.brain:
            return await self.error("INVALID_SESSION", "Send InitializeAvatarSession first.", request_id)
        await self.cancel_reply("persona_change")
        environment = self.brain.environment
        self.brain = BrainContext(persona=get_persona(payload.get("persona")), max_history=self.brain.max_history, environment=environment)
        await self.on_initialize({"persona": self.brain.persona.id, "context": environment}, request_id)

    # ------------------------------------------------------------ main loop
    rate: ConnectionRate = field(default_factory=lambda: ConnectionRate(limit=_limit("ESHB_AVATAR_TURNS_PER_MINUTE", 30)))
    transport: Any = None

    async def dispatch(self, raw: str) -> None:
        if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
            return await self.error("INVALID_MESSAGE", "Message too large.")
        try:
            message = json.loads(raw)
            header = message["header"]
            name = header["name"]
            request_id = str(header.get("request_id") or uuid.uuid4().hex[:12])[:64]
            payload = message.get("payload") or {}
            if not isinstance(payload, dict):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            return await self.error("INVALID_MESSAGE", "Expected {header: {name, request_id}, payload}.")
        if name not in CLIENT_MESSAGES:
            return await self.error("INVALID_MESSAGE", f"Unknown message {str(name)[:40]}.", request_id)
        if name == "TriggerHeartbeat":
            return await self.send("AvatarHeartbeat", None, request_id)
        if name == "InitializeAvatarSession":
            return await self.on_initialize(payload, request_id)
        if not self.initialized:
            return await self.error("INVALID_SESSION", "Send InitializeAvatarSession first.", request_id)
        if name == "SendHumanText":
            return await self.on_human_text(payload, request_id)
        if name == "Interrupt":
            return await self.on_interrupt(request_id)
        if name == "EndSpeech":
            return await self.on_end_speech(payload)
        if name == "UpdateContext":
            return await self.on_update_context(payload)
        if name == "SetPersona":
            return await self.on_set_persona(payload, request_id)

    async def run(self) -> None:
        heartbeat = _limit("ESHB_AVATAR_HEARTBEAT_TIMEOUT", 30)
        ttl = _limit("ESHB_AVATAR_CONNECTION_TTL", 900)
        while True:
            now = time.monotonic()
            if now - self.last_seen > heartbeat:
                await self.error("HEARTBEAT_TIMEOUT", f"No heartbeat for {heartbeat} seconds.")
                return
            if now - self.started > ttl:
                await self.error("INVALID_SESSION", "Session time limit reached. Start a new chat.")
                return
            try:
                raw = await asyncio.wait_for(self.websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            self.last_seen = time.monotonic()
            await self.dispatch(raw)


def _clean_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, item in list(value.items())[:12]:
        if isinstance(item, (str, int, float, bool)) or item is None:
            clean[str(key)[:40]] = str(item)[:500] if isinstance(item, str) else item
    return clean


async def avatar_socket(websocket: WebSocket, transport: Any = None) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=1008, reason="WebSocket origin not allowed")
        return
    if not SESSIONS.acquire(_limit("ESHB_AVATAR_MAX_SESSIONS", 20)):
        await websocket.close(code=1013, reason="Too many live avatar chats right now. Try again shortly.")
        return
    await websocket.accept()
    session = AvatarSession(websocket)
    session.transport = transport
    try:
        await session.run()
    except WebSocketDisconnect:
        pass
    except RuntimeError:  # socket closed while sending
        pass
    finally:
        if session.reply_task and not session.reply_task.done():
            session.reply_task.cancel()
        SESSIONS.release()
        try:
            await websocket.close()
        except RuntimeError:
            pass


def avatar_status() -> dict[str, Any]:
    status = llm_status()
    return {
        "websocket": "/ws/avatar",
        "protocol": "OpenAvatarChat session protocol (text + control subset) with AvatarSpeech/AvatarCard extensions",
        "personas": [p.public() for p in PERSONAS.values()],
        "llm": {"configured": status["configured"], "model": status["model"], "api": status["api"]},
        "speech": "browser speech recognition and synthesis (no audio leaves the browser except as recognized text)",
        "avatar": "browser-rendered SVG avatar driven by ARKit blendshape channels",
        "active_sessions": SESSIONS.active,
        "max_sessions": _limit("ESHB_AVATAR_MAX_SESSIONS", 20),
    }
