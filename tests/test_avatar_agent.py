"""The guide as the centre of the platform: tool calling, any-language teaching, neural voice and expressions."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.avatar_chat import brain, tools, voice
from app.avatar_chat.brain import BrainContext, localize_events, think
from app.avatar_chat.personas import LANGUAGES, get_persona


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.setenv("ESHB_WARMUP", "false")
    for name in ("OPENAI_API_KEY", "ESHB_TTS_PROVIDER", "AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION",
                 "UNIVERSAL_MT_BASE_URL", "GOOGLE_CLOUD_TRANSLATE_API_KEY", "ESHB_AVATAR_LLM_API"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(brain, "DEFAULT_TRANSPORT", None)
    monkeypatch.setattr(voice, "DEFAULT_TRANSPORT", None)
    voice._CACHE.clear()


def model_on(monkeypatch, api="responses"):
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    if api == "chat":
        monkeypatch.setenv("ESHB_AVATAR_LLM_API", "chat_completions")


def sse(events: list) -> bytes:
    return "".join(f"data: {json.dumps(e) if not isinstance(e, str) else e}\n\n" for e in events).encode()


def scripted(rounds: list[list], seen: list) -> httpx.MockTransport:
    """Each model request gets the next scripted list of SSE events."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=sse(rounds[len(seen) - 1]))
    return httpx.MockTransport(handler)


def collect(gen):
    async def run():
        return [event async for event in gen]
    return asyncio.run(run())


def fn_call(name: str, args: dict, call_id: str = "call_1") -> dict:
    return {"type": "response.output_item.done",
            "item": {"id": "fc_" + call_id, "type": "function_call", "call_id": call_id, "name": name, "arguments": json.dumps(args)}}


def text(*chunks: str) -> list[dict]:
    return [{"type": "response.output_text.delta", "delta": c} for c in chunks] + [{"type": "response.completed"}]


# ------------------------------------------------------------------ tool calling
def test_responses_api_tool_loop(monkeypatch):
    model_on(monkeypatch)
    seen: list = []
    transport = scripted([
        [fn_call("translate_ancient", {"text": "the king made a great house", "source_language": "english", "target_languages": ["archaic_sumerian"]})],
        text("In Sumerian that's lugal-e e2 gal mu-un-du3."),
    ], seen)
    ctx = BrainContext(persona=get_persona("nefer"))
    events = collect(think(ctx, "How do I say the king made a great house in Sumerian?", transport))
    kinds = [e["type"] for e in events]
    assert kinds[:2] == ["tool", "card"] and events[1]["card"]["rows"][0]["text"] == "lugal-e e2 gal mu-un-du3"
    assert "".join(e["text"] for e in events if e["type"] == "delta").startswith("In Sumerian")
    follow_up = seen[1]["input"]
    call_item = next(i for i in follow_up if i.get("type") == "function_call")
    output_item = next(i for i in follow_up if i.get("type") == "function_call_output")
    assert call_item["call_id"] == output_item["call_id"] == "call_1"
    assert json.loads(output_item["output"])["translations"]["archaic_sumerian"]["text"] == "lugal-e e2 gal mu-un-du3"


def test_chat_completions_tool_loop_teaches_any_language(monkeypatch):
    model_on(monkeypatch, "chat")
    args = json.dumps({"language": "French", "phrase": "Bonjour mon ami", "translation": "Hello my friend", "direction": "left_to_right",
                       "words": [{"original": "Bonjour", "transliteration": "bonjour", "pronunciation": "bon-ZHOOR", "meaning": "hello"},
                                 {"original": "mon", "transliteration": "mon", "pronunciation": "mohn", "meaning": "my"},
                                 {"original": "ami", "transliteration": "ami", "pronunciation": "ah-MEE", "meaning": "friend"}]})
    first = [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "teach_phrase", "arguments": args[:40]}}]}}]},
             {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": args[40:]}}]}, "finish_reason": "tool_calls"}]}, "[DONE]"]
    second = [{"choices": [{"delta": {"content": "Let's say it together: bon-ZHOOR mohn ah-MEE."}}]}, "[DONE]"]
    seen: list = []
    ctx = BrainContext(persona=get_persona("nefer"))
    events = collect(think(ctx, "Teach me to greet a friend in French", scripted([first, second], seen)))
    lesson = next(e["reading"] for e in events if e["type"] == "reading")
    assert [s["pronunciation"] for s in lesson["segments"]] == ["bon-ZHOOR", "mohn", "ah-MEE"]
    assert ctx.lesson is lesson
    assert seen[1]["messages"][-2]["tool_calls"][0]["function"]["name"] == "teach_phrase"
    assert seen[1]["messages"][-1]["role"] == "tool" and seen[1]["messages"][-1]["tool_call_id"] == "c1"
    # The quiz then runs deterministically on the model's lesson, offline-fast.
    quiz = collect(think(ctx, "quiz me", scripted([], [])))
    assert quiz[1]["segment"] == 0
    assert collect(think(ctx, "bonjour", scripted([], [])))[0]["correct"] is True


def test_start_quiz_tool_stops_the_turn(monkeypatch):
    model_on(monkeypatch)
    seen: list = []
    ctx = BrainContext(persona=get_persona("nefer"))
    brain.lesson_turn(ctx, "𓋹𓈖𓐍 𓄤𓆑𓂋")
    events = collect(think(ctx, "Let us see whether those words stuck with me", scripted([[fn_call("start_quiz", {})]], seen)))
    says = [e for e in events if e["type"] == "say"]
    assert says[0]["quiz"] == "start" and says[1]["segment"] == 0
    assert len(seen) == 1 and ctx.quiz is not None  # no second model round talking over the question


def test_app_actions_and_bad_tool_calls():
    ctx = BrainContext(persona=get_persona("nefer"))
    outcome = asyncio.run(tools.execute(ctx, "app_action", {"action": "read_camera"}))
    assert outcome.events == [{"type": "action", "action": "read_camera"}]
    assert not asyncio.run(tools.execute(ctx, "app_action", {"action": "open_tab", "tab": "../admin"})).output["ok"]
    assert "Unknown tool" in asyncio.run(tools.execute(ctx, "rm_rf", {})).output["error"]
    assert "JSON object" in asyncio.run(tools.execute(ctx, "read_script", "not json")).output["error"]
    assert "Bad arguments" in asyncio.run(tools.execute(ctx, "read_script", {"nope": 1})).output["error"]
    caps = asyncio.run(tools.execute(ctx, "list_capabilities", {})).output
    assert "archaic_sumerian" in caps["ancient_languages"] and caps["voice"] == "browser"


def test_tool_specs_are_valid_for_both_apis():
    names = {spec["name"] for spec in tools.TOOL_SPECS}
    assert names == tools.TOOL_NAMES and len(names) == 8
    for spec in tools.responses_tools():
        assert spec["type"] == "function" and spec["parameters"]["type"] == "object"
    for spec in tools.chat_tools():
        assert spec["function"]["parameters"]["additionalProperties"] is False


def test_modern_translation_tool(monkeypatch):
    out = asyncio.run(tools.execute(None, "translate_modern", {"text": "hello", "source_language": "en", "target_language": "fr"}))
    assert out.output["available"] is False and "your own translation" in out.output["instruction"]
    monkeypatch.setenv("GOOGLE_CLOUD_TRANSLATE_API_KEY", "g-test")
    import app.universal_translation as ut

    async def fake(req):
        return {"translation": "bonjour", "provider": "google-cloud", "target_language": "fr"}
    monkeypatch.setattr(ut, "universal_translate", fake)
    out = asyncio.run(tools.execute(None, "translate_modern", {"text": "hello", "source_language": "en", "target_language": "fr"}))
    assert out.output["translation"] == "bonjour" and out.events[0]["card"]["rows"][0]["status"] == "machine_translation"


# ------------------------------------------------------------------ any learner language
def test_learner_languages_and_greetings():
    assert {"english", "swahili", "french", "chinese", "russian", "german", "amharic"} <= set(LANGUAGES)
    persona = get_persona("nefer").localized("chinese")
    assert persona.voice_lang == "zh-CN" and "Nefer" in persona.greeting


def test_lessons_are_translated_for_other_languages(monkeypatch):
    ctx = BrainContext(persona=get_persona("nefer").localized("french"))
    events = brain.lesson_turn(ctx, "𓋹𓈖𓐍")
    offline = asyncio.run(localize_events(events, ctx))
    assert offline[0]["type"] == "notice" and "Français" in offline[0]["text"]
    assert asyncio.run(localize_events(events, ctx))[0]["type"] != "notice"  # the notice is said once
    monkeypatch.setenv("GOOGLE_CLOUD_TRANSLATE_API_KEY", "g-test")
    import app.universal_translation as ut

    async def fake(req):
        items = json.loads(req.text)
        return {"translation": json.dumps([{"text": "FR: " + i["text"]} for i in items]), "provider": "google-cloud"}
    monkeypatch.setattr(ut, "universal_translate", fake)
    translated = asyncio.run(localize_events(events, ctx))
    says = [e for e in translated if e["type"] == "say"]
    assert all(e["text"].startswith("FR: ") for e in says)
    assert [e.get("segment") for e in says] == [e.get("segment") for e in events if e["type"] == "say"]


def test_lessons_translated_by_model_when_no_provider(monkeypatch):
    model_on(monkeypatch)
    ctx = BrainContext(persona=get_persona("nefer").localized("german"))
    events = brain.lesson_turn(ctx, "𓋹𓈖𓐍")
    lines = [e["text"] for e in events if e["type"] == "say"]
    reply = json.dumps([f"DE {i}" for i in range(len(lines))])
    out = asyncio.run(localize_events(events, ctx, scripted([text(reply)], [])))
    assert [e["text"] for e in out if e["type"] == "say"] == [f"DE {i}" for i in range(len(lines))]


# ------------------------------------------------------------------ voice
def test_voice_defaults_to_browser():
    assert voice.tts_status() == {"provider": "browser", "model": None, "server_audio": False}
    assert asyncio.run(voice.synthesize("hi", get_persona("nefer"), "english")) is None


def test_openai_voice_with_intonation_and_cache(monkeypatch):
    monkeypatch.setenv("ESHB_TTS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, content=b"ID3mp3bytes")
    monkeypatch.setattr(voice, "DEFAULT_TRANSPORT", httpx.MockTransport(handler))
    persona = get_persona("amani")
    out = asyncio.run(voice.synthesize("Vizuri sana!", persona, "swahili", "happy", 0.92))
    assert out["mime"] == "audio/mpeg" and out["audio"]
    body = calls[0]
    assert body["voice"] == "sage" and body["model"] == "gpt-4o-mini-tts" and body["response_format"] == "mp3"
    assert "delighted" in body["instructions"] and "Kiswahili" in body["instructions"]
    asyncio.run(voice.synthesize("Vizuri sana!", persona, "swahili", "happy", 0.92))
    assert len(calls) == 1  # cached
    monkeypatch.setenv("ESHB_TTS_MODEL", "tts-1")
    asyncio.run(voice.synthesize("Hello", persona, "english"))
    assert "instructions" not in calls[-1]


def test_azure_voice_ssml(monkeypatch):
    monkeypatch.setenv("ESHB_TTS_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_SPEECH_KEY", "az")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "westeurope")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=b"mp3")
    monkeypatch.setattr(voice, "DEFAULT_TRANSPORT", httpx.MockTransport(handler))
    asyncio.run(voice.synthesize("Habari <rafiki> & karibu", get_persona("amani"), "swahili", "warm", 0.92))
    request = seen[0]
    assert request.url.host == "westeurope.tts.speech.microsoft.com"
    assert request.headers["Ocp-Apim-Subscription-Key"] == "az" and request.headers["Content-Type"] == "application/ssml+xml"
    ssml = request.content.decode()
    assert "sw-KE-ZuriNeural" in ssml and "&lt;rafiki&gt; &amp; karibu" in ssml and 'rate="-3%"' in ssml


def test_emotions():
    assert voice.emotion_for("x", {"correct": True}) == "happy"
    assert voice.emotion_for("x", {"correct": False}) == "encouraging"
    assert voice.emotion_for("Word 1 is said ankh", {"segment": 0}) == "teaching"
    assert voice.emotion_for("What does it mean?") == "curious"
    assert voice.emotion_for("Habari, karibu!") == "warm"


# ------------------------------------------------------------------ session with server voice
def msg(name, payload=None):
    return json.dumps({"header": {"name": name, "request_id": "r"}, "payload": payload or {}})


def recv(ws):
    m = json.loads(ws.receive_text())
    return m["header"]["name"], m.get("payload") or {}


def test_session_server_voice_keeps_order(monkeypatch):
    monkeypatch.setenv("ESHB_TTS_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    offline = lambda: {"configured": False, "api": "responses", "model": None, "base_url": "", "offline_fallback": True}
    monkeypatch.setattr(brain, "llm_status", offline)
    import app.avatar_chat.session as session
    monkeypatch.setattr(session, "llm_status", offline)

    async def handler(request):
        text_in = json.loads(request.content)["input"]
        if text_in.startswith("This is written"):
            await asyncio.sleep(0.3)  # the first sentence is the slowest to synthesize
        if "Egyptologists" in text_in:
            return httpx.Response(500)
        return httpx.Response(200, content=("AUDIO:" + text_in[:10]).encode())
    monkeypatch.setattr(voice, "DEFAULT_TRANSPORT", httpx.MockTransport(handler))
    from app.main import app
    with TestClient(app) as client, client.websocket_connect("/ws/avatar") as ws:
        ws.send_text(msg("InitializeAvatarSession", {"persona": "nefer"}))
        init = recv(ws)[1]
        assert init["voice"]["provider"] == "openai" and init["voice"]["server_audio"] is True
        names = [recv(ws) for _ in range(4)]
        greeting = next(p for n, p in names if n == "AvatarSpeech")
        assert greeting["audio"] and greeting["emotion"] == "warm"
        ws.send_text(msg("SendHumanText", {"text": "𓋹𓈖𓐍 𓄤𓆑𓂋", "end_of_speech": True}))
        recv(ws)
        speech, ended = [], False
        while not ended:
            name, payload = recv(ws)
            if name == "AvatarSpeech" and payload.get("text"):
                speech.append(payload)
            ended = name == "ChatSignal" and payload["type"] == "stream_end" and payload["stream_type"] == "avatar_text"
        assert [p["index"] for p in speech] == sorted(p["index"] for p in speech)
        assert speech[0]["text"].startswith("This is written") and speech[0]["audio"]
        failed = next(p for p in speech if "Egyptologists" in p["text"])
        assert "audio" not in failed and "HTTP 500" in failed["voice_error"]  # that sentence falls back to the browser voice
        assert {p["emotion"] for p in speech if p.get("segment") is not None} == {"teaching"}


def test_session_accepts_any_learner_language(monkeypatch):
    from app.main import app
    with TestClient(app) as client, client.websocket_connect("/ws/avatar") as ws:
        ws.send_text(msg("InitializeAvatarSession", {"persona": "theo", "language": "russian"}))
        init = recv(ws)[1]
        assert init["language"] == "russian" and len(init["languages"]) == len(LANGUAGES)
        greeting = [recv(ws) for _ in range(4)]
        speech = next(p for n, p in greeting if n == "AvatarSpeech")
        assert speech["voice"]["lang"] == "ru-RU" and speech["text"].startswith("Здравствуйте")
