"""Live avatar chat: text tools, motion data, brain (offline + mocked LLM) and the WebSocket protocol."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.avatar_chat import brain
from app.avatar_chat.brain import BrainContext, compile_prompt, llm_status, run_tools, stream_llm, think
from app.avatar_chat.personas import PERSONAS, get_persona
from app.avatar_chat.text_tools import SentenceBuffer, TokenBuffer, speakable
from app.avatar_chat.visemes import CHANNELS, VISEMES, motion_track, visemes_for


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(brain, "DEFAULT_TRANSPORT", None)


# ------------------------------------------------------------------ text tools
def test_token_buffer_never_splits_words():
    buffer = TokenBuffer()
    out = "".join(buffer.process(t) for t in ["Hel", "lo wo", "rld, ", "ʾamān"]) + buffer.flush()
    assert out == "Hello world, ʾamān"
    assert TokenBuffer().process("Hel") == ""


def test_sentence_buffer_emits_whole_sentences_in_any_script():
    buffer = SentenceBuffer()
    got = []
    for token in ["The king ", "made a house. ", "Mfalme ", "alikuja! ", "ተወከልኩ፡በአማን።", " Next"]:
        got += buffer.process(token)
    got += buffer.flush()
    assert got == ["The king made a house.", "Mfalme alikuja!", "ተወከልኩ፡በአማን።", "Next"]


def test_speakable_strips_markdown_but_keeps_scripts():
    text = "**Truth** is `mꜣꜥt` — see [the card](http://x).\n- 𒃻𒄀𒈾\n```code```"
    assert speakable(text) == "Truth is mꜣꜥt — see the card. 𒃻𒄀𒈾"


# ------------------------------------------------------------------ motion
def test_visemes_and_motion_track():
    assert visemes_for("map") == ["PP", "AA", "PP"]
    assert visemes_for("the shoe")[:3] == ["TH", "E", "sil"]
    track = motion_track("Hello there.", rate=1.0)
    assert track["channels"] == CHANNELS
    assert track["frames"][0]["t"] == 0 and track["duration"] > 0.3
    assert all(set(f["w"]) <= set(CHANNELS) for f in track["frames"])
    assert all(set(weights) <= set(CHANNELS) for weights in VISEMES.values())
    slow = motion_track("Hello there.", rate=0.5)
    assert slow["duration"] > track["duration"]


# ------------------------------------------------------------------ brain (offline)
def test_tools_translate_meaning_and_languages():
    nefer = get_persona("nefer")
    [tool] = run_tools("How do you say the king loved the good mother in Latin?", nefer)
    assert tool.name == "translate" and tool.card["rows"][0]["text"] == "rex matrem duenam amauet"
    assert "grammar rules" in tool.reply
    [tool] = run_tools("What does lugal mean?", nefer)
    assert tool.reply == 'lugal is Archaic Sumerian for "king".'
    [tool] = run_tools("translate water into every language", nefer)
    assert len(tool.card["rows"]) == 11 and "card" in tool.reply
    [tool] = run_tools("which languages do you know?", nefer)
    assert "Proto-Semitic" in tool.reply
    [tool] = run_tools("What does spaceship mean?", nefer)
    assert "won't guess" in tool.reply


def test_swahili_persona_answers_in_swahili():
    amani = get_persona("amani")
    [tool] = run_tools("Tafsiri mfalme alipenda mama kwa Kilatini", amani)
    assert tool.reply.startswith("Kwa Kilatini cha kale, ni rex matrem amauet.")
    [tool] = run_tools("Maana ya lugal ni nini?", amani)
    assert "mfalme" in tool.reply


def test_untranslatable_and_open_questions_are_honest():
    nefer = get_persona("nefer")
    [tool] = run_tools("translate the spaceship hummed into Latin", nefer)
    assert tool.data["ok"] is False and "couldn't" in tool.reply
    reply = brain.offline_reply("What is the weather?", nefer, [])
    assert "No language model is connected" in reply


def _collect(gen):
    async def run():
        return [event async for event in gen]
    return asyncio.run(run())


def test_think_offline_streams_card_then_words():
    ctx = BrainContext(persona=get_persona("nefer"))
    events = _collect(think(ctx, "What is water in Ge'ez?"))
    assert events[0]["type"] == "card"
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text == "In Ge'ez (Classical Ethiopic), it is māy."


def test_prompt_compiler_layers():
    ctx = BrainContext(persona=get_persona("theo"), environment={"active_tab": "ladder", "junk": ""})
    ctx.remember("user", "hi")
    ctx.remember("assistant", "hello")
    tools = run_tools("How do you say water in Latin?", ctx.persona)
    system, messages = compile_prompt(ctx, "How do you say water in Latin?", tools)
    assert system.index("Rules:") < system.index("[Persona]") < system.index("\n<environment-state>\n")
    assert '"aqua"' in system and "active_tab" in system and "junk" not in system
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]


# ------------------------------------------------------------------ brain (mocked language model)
def _sse(lines: list[str]) -> bytes:
    return "".join(f"data: {line}\n\n" for line in lines).encode()


def responses_transport(chunks: list[str], seen: list | None = None, delay: float = 0.0):
    async def body():
        for chunk in chunks:
            if delay:
                await asyncio.sleep(delay)
            yield _sse([json.dumps({"type": "response.output_text.delta", "delta": chunk})])
        yield _sse([json.dumps({"type": "response.completed"}), "[DONE]"])

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body())
    return httpx.MockTransport(handler)


def test_llm_responses_api_streaming(monkeypatch):
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_status()["configured"] and llm_status()["api"] == "responses"
    seen: list[httpx.Request] = []
    ctx = BrainContext(persona=get_persona("nefer"))
    events = _collect(think(ctx, "How do you say water in Latin?", responses_transport(["Aqua ", "is water."], seen)))
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Aqua is water."
    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/responses") and body["stream"] is True
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    assert {tool["name"] for tool in body["tools"]} >= {"translate_ancient", "read_script", "teach_phrase", "app_action"}
    assert "English" in body["instructions"]  # the learner's language is in the prompt


def test_llm_chat_completions_api(monkeypatch):
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("ESHB_AVATAR_LLM_API", "chat_completions")
    monkeypatch.setenv("ESHB_AVATAR_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("ESHB_AVATAR_LLM_MODEL", "llama3")
    assert llm_status()["configured"]  # local endpoints need no key

    def handler(request):
        body = json.loads(request.content)
        assert body["messages"][0]["role"] == "system" and body["model"] == "llama3"
        lines = [json.dumps({"choices": [{"delta": {"content": c}}]}) for c in ["Jambo", "!"]] + ["[DONE]"]
        return httpx.Response(200, content=_sse(lines))
    out = _collect(stream_llm("sys", [{"role": "user", "content": "hi"}], httpx.MockTransport(handler)))
    assert out == ["Jambo", "!"]


def test_llm_failure_falls_back_to_tools(monkeypatch):
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": "bad key"}))
    events = _collect(think(BrainContext(persona=get_persona("nefer")), "What does lugal mean?", transport))
    assert events[0]["type"] == "notice" and "401" in events[0]["text"]
    assert "".join(e["text"] for e in events if e["type"] == "delta") == 'lugal is Archaic Sumerian for "king".'


# ------------------------------------------------------------------ WebSocket protocol
def msg(name, payload=None, request_id="r1"):
    return json.dumps({"header": {"name": name, "request_id": request_id}, "payload": payload or {}})


def recv(ws):
    m = json.loads(ws.receive_text())
    return m["header"]["name"], m.get("payload") or {}, m["header"]["request_id"]


def init(ws, persona="nefer"):
    ws.send_text(msg("InitializeAvatarSession", {"persona": persona, "context": {"active_tab": "avatar"}}))
    received = [recv(ws) for _ in range(5)]
    names = [r[0] for r in received]
    assert names == ["AvatarSessionInitialized", "ChatSignal", "EchoAvatarText", "AvatarSpeech", "ChatSignal"]
    return received


def until_reply_end(ws):
    events = []
    while True:
        name, payload, rid = recv(ws)
        events.append((name, payload))
        if name == "ChatSignal" and payload["type"] in {"stream_end", "stream_cancel"} and payload["stream_type"] == "avatar_text":
            return events


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_session_greeting_and_turn(client):
    with client.websocket_connect("/ws/avatar") as ws:
        received = init(ws)
        payload = received[0][1]
        assert payload["persona"]["id"] == "nefer" and "snapshot" not in payload["persona"]
        assert len(payload["personas"]) == len(PERSONAS) and payload["llm"]["configured"] is False
        assert received[3][1]["motion"]["frames"] and received[3][1]["voice"]["lang"] == "en-US"
        ws.send_text(msg("SendHumanText", {"stream_key": "s1", "text": "How do you say the king made a great house in ", "end_of_speech": False}))
        ws.send_text(msg("SendHumanText", {"stream_key": "s1", "text": "Sumerian?", "end_of_speech": True}, "r2"))
        name, payload, rid = recv(ws)
        assert name == "EchoHumanText" and payload["text"].endswith("in Sumerian?") and rid == "r2"
        events = until_reply_end(ws)
        names = [n for n, _ in events]
        begin = next(p for n, p in events if n == "ChatSignal" and p["type"] == "stream_begin")
        assert begin["parent_stream_keys"] == [payload["stream_key"]]
        card = next(p for n, p in events if n == "AvatarCard")["card"]
        assert card["rows"][0]["text"] == "lugal-e e2 gal mu-un-du3"
        speech = [p for n, p in events if n == "AvatarSpeech"]
        assert speech[0]["text"] == "In Archaic Sumerian, it is lugal-e e2 gal mu-un-du3."
        assert speech[-1]["end_of_speech"] is True
        increments = "".join(p["text"] for n, p in events if n == "EchoAvatarText")
        assert increments.startswith("In Archaic Sumerian") and names.index("AvatarCard") < names.index("EchoAvatarText")
        ws.send_text(msg("EndSpeech", {"stream_key": speech[-1]["stream_key"]}))
        name, payload, _ = recv(ws)
        assert name == "ChatSignal" and payload["stream_type"] == "client_playback"
        ws.send_text(msg("TriggerHeartbeat", request_id="hb"))
        assert recv(ws)[0::2] == ("AvatarHeartbeat", "hb")


def test_interrupt_cancels_streaming_reply(client, monkeypatch):
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    words = [f"word{i} " for i in range(200)]
    monkeypatch.setattr(brain, "DEFAULT_TRANSPORT", responses_transport(words, delay=0.02))
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SendHumanText", {"stream_key": "s1", "text": "Tell me a long story", "end_of_speech": True}))
        assert recv(ws)[0] == "EchoHumanText"
        assert recv(ws)[1]["type"] == "stream_begin"
        first = recv(ws)
        assert first[0] == "EchoAvatarText"
        ws.send_text(msg("Interrupt", request_id="int"))
        seen = []
        while True:
            name, payload, rid = recv(ws)
            seen.append(name)
            if name == "InterruptAccepted":
                assert rid == "int" and payload["stream_key"] == first[1]["stream_key"]
                break
        assert "ChatSignal" in seen  # the stream_cancel signal precedes acceptance
        # The cancelled reply is not remembered, and the session keeps working.
        monkeypatch.setattr(brain, "DEFAULT_TRANSPORT", responses_transport(["Sure."]))
        ws.send_text(msg("SendHumanText", {"stream_key": "s2", "text": "hi", "end_of_speech": True}))
        events = until_reply_end(ws)
        assert any(n == "AvatarSpeech" and p["text"] == "Sure." for n, p in events)


def test_new_turn_barges_in_on_reply(client, monkeypatch):
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(brain, "DEFAULT_TRANSPORT", responses_transport([f"w{i} " for i in range(200)], delay=0.02))
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SendHumanText", {"stream_key": "a", "text": "first", "end_of_speech": True}))
        for _ in range(3):
            recv(ws)
        ws.send_text(msg("SendHumanText", {"stream_key": "b", "text": "second", "end_of_speech": True}))
        names = []
        while "InterruptNotification" not in names:
            names.append(recv(ws)[0])


def test_protocol_errors(client):
    with client.websocket_connect("/ws/avatar") as ws:
        ws.send_text(msg("SendHumanText", {"text": "hi"}))
        name, payload, _ = recv(ws)
        assert name == "Error" and payload["code"] == "INVALID_SESSION"
        ws.send_text("not json")
        assert recv(ws)[1]["code"] == "INVALID_MESSAGE"
        ws.send_text(msg("RemoteShell"))
        assert recv(ws)[1]["code"] == "INVALID_MESSAGE"
        ws.send_text(msg("SendHumanText", {"text": "x" * 20_000}))
        assert recv(ws)[1]["message"] == "Message too large."
        ws.send_text("x" * 8_000_000)
        assert recv(ws)[1]["message"] == "Message too large."
        init(ws)
        ws.send_text(msg("SendHumanText", {"stream_key": "big", "text": "a" * 2001, "end_of_speech": True}))
        assert recv(ws)[1]["code"] == "INVALID_MESSAGE"


def test_persona_switch_and_swahili_voice(client):
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SetPersona", {"persona": "amani"}))
        received = [recv(ws) for _ in range(5)]
        assert received[0][1]["persona"]["id"] == "amani"
        assert received[3][1]["voice"]["lang"] == "sw-KE" and received[3][1]["text"].startswith("Habari")


def test_heartbeat_timeout_closes_session(client, monkeypatch):
    monkeypatch.setenv("ESHB_AVATAR_HEARTBEAT_TIMEOUT", "1")
    with client.websocket_connect("/ws/avatar") as ws:
        name, payload, _ = recv(ws)
        assert name == "Error" and payload["code"] == "HEARTBEAT_TIMEOUT"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


def test_session_limit(client, monkeypatch):
    monkeypatch.setenv("ESHB_AVATAR_MAX_SESSIONS", "1")
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/avatar") as second:
                second.receive_text()
        assert excinfo.value.code == 1013


def test_turn_rate_limit(client, monkeypatch):
    monkeypatch.setenv("ESHB_AVATAR_TURNS_PER_MINUTE", "1")
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SendHumanText", {"stream_key": "a", "text": "hello", "end_of_speech": True}))
        recv(ws)
        until_reply_end(ws)
        ws.send_text(msg("SendHumanText", {"stream_key": "b", "text": "hello again", "end_of_speech": True}))
        assert recv(ws)[1]["code"] == "RATE_LIMIT"


def test_status_endpoints(client):
    status = client.get("/api/avatar/status").json()
    assert status["websocket"] == "/ws/avatar" and status["llm"]["configured"] is False
    assert {p["id"] for p in client.get("/api/avatar/personas").json()["personas"]} == set(PERSONAS)
    caps = client.get("/api/capabilities").json()
    assert caps["features"]["live_avatar_chat"] is True and caps["avatar_chat"]["websocket"] == "/ws/avatar"


def test_cross_origin_socket_rejected(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/avatar", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_text()
    assert excinfo.value.code == 1008
