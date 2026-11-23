"""Reading lessons, tutor mode and seeing (photos / live camera) for the live avatar chat."""
from __future__ import annotations

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from app.avatar_chat import brain, reading, tutor
from app.avatar_chat.brain import BrainContext, lesson_turn, see
from app.avatar_chat.personas import get_persona

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()

WALL = {
    "is_text_present": True, "script": "hieroglyphic", "language": "Middle Egyptian", "reading_direction": "right_to_left",
    "direction_reason": "The birds face right, so we start on the right.", "summary": "A carved line on a wall.",
    "segments": [
        {"original": "𓋹𓈖𓐍", "transliteration": "ꜥnḫ", "pronunciation": "ankh", "meaning_english": "life", "meaning_learner": "life", "confidence": 0.9},
        {"original": "𓄤", "transliteration": "ḥtp", "pronunciation": "hetep", "meaning_english": "peace", "meaning_learner": "peace", "confidence": 0.5},
        {"original": "", "transliteration": "ḥtp-dj-nswt", "pronunciation": "hetep di nesut", "meaning_english": "an offering the king gives",
         "meaning_learner": "an offering the king gives", "confidence": 0.6},
    ],
    "translation_english": "Life, an offering the king gives", "translation_learner": "Life, an offering the king gives",
    "uncertainties": ["Lower register damaged."], "overall_confidence": 0.7,
}


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.setenv("ESHB_WARMUP", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(brain, "DEFAULT_TRANSPORT", None)


def with_vision_model(monkeypatch, result=WALL, error=None):
    """Configure a vision model whose answer is mocked; the chat model stays offline."""
    monkeypatch.setenv("ESHB_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    offline = lambda: {"configured": False, "api": "responses", "model": None, "base_url": "", "offline_fallback": True}
    monkeypatch.setattr(brain, "llm_status", offline)
    import app.ai as ai
    import app.avatar_chat.session as session
    monkeypatch.setattr(session, "llm_status", offline)
    calls = []

    async def fake(content, instructions):
        calls.append((content, instructions))
        if error:
            raise error
        return json.loads(json.dumps(result))
    monkeypatch.setattr(ai, "_responses_request", fake)
    return calls


def collect(gen):
    async def run():
        return [event async for event in gen]
    return asyncio.run(run())


# ------------------------------------------------------------------ pronunciation and scripts
@pytest.mark.parametrize("translit,spoken", [
    ("nfr", "nefer"), ("ꜥnḫ", "ankh"), ("ḥtp", "hetep"), ("mꜣꜥt", "maat"), ("nṯr", "netjer"),
    ("jtrw", "iteru"), ("sḏm", "sedjem"), ("nswt", "nesut"), ("rꜥ", "ra"), ("ptḥ", "ptah"),
])
def test_egyptological_pronunciation(translit, spoken):
    assert reading.egyptian_pronunciation(translit) == spoken


def test_detect_script_and_ratio():
    assert reading.detect_script("Read 𓋹 please") == "hieroglyphic"
    assert reading.detect_script("𒈗") == "cuneiform"
    assert reading.detect_script("ተወከልኩ") == "ethiopic"
    assert reading.detect_script("hello") is None
    assert reading.native_script_ratio("Read this to me: 𓋹𓈖𓐍 𓄤𓆑𓂋") >= 0.25
    assert reading.native_script_ratio("translate water") == 0


def test_hieroglyphs_group_complements_into_words():
    r = reading.read_text("𓋹𓈖𓐍𓄤𓆑𓂋", "english")
    assert [(s["transliteration"], s["pronunciation"], s["meaning"]["english"]) for s in r["segments"]] == [("ꜥnḫ", "ankh", "life"), ("nfr", "nefer", "good")]
    roles = [sign["role"] for sign in r["segments"][0]["signs"]]
    assert roles == ["triliteral", "complement", "complement"]
    assert r["translation"]["english"] == "life, good" and r["translation"]["status"] == "word_by_word"


def test_hieroglyph_sentence_uses_grammar_and_unicode_codes():
    r = reading.read_text("𓎔𓈖𓀀 𓄣𓏤𓀀 𓅓 𓐙𓂝𓏏𓆄", "english")
    assert r["translation"]["english"] == "I trusted in the truth" and r["translation"]["status"] == "grammar_parse"
    assert r["language"] == "old_egyptian"
    assert r["segments"][3]["signs"][0]["code"] == "Aa11"  # outside the teaching catalog, named from Unicode
    assert reading.gardiner_from_unicode("𓋹") == "S34"


def test_cuneiform_marks_grammar_affixes():
    r = reading.read_text("𒈗𒂊 𒂍 𒃲 𒈬𒌦𒆕", "english")
    assert r["translation"]["english"] == "The king made the great house"
    first = r["segments"][0]
    assert first["transliteration"] == "lugal-e" and first["signs"][1]["role"] == "affix"
    assert r["segments"][-1]["meaning"]["english"] == "He made"


@pytest.mark.parametrize("text,lang,expected", [
    ("ተወከልኩ፡በአማን።", "geez", "I trusted in the truth"),
    ("𐌖𐌄𐌓𐌉𐌕𐌀𐌕𐌄𐌉·𐌂𐌓𐌄𐌃𐌉𐌃𐌄𐌉", "old_latin", "I trusted in the truth"),
    ("توكلت على الحق", "old_arabic", "I trusted in the truth"),
])
def test_alphabetic_scripts(text, lang, expected):
    r = reading.read_text(text, "english")
    assert r["language"] == lang and r["translation"]["english"] == expected
    assert all(s["status"] == "confirmed" for s in r["segments"])


def test_letters_show_sounds_not_names():
    latin = reading.read_text("𐌂𐌓𐌄𐌃𐌉𐌃𐌄𐌉", "english")
    assert [s["value"] for s in latin["segments"][0]["signs"][:4]] == ["c", "r", "e", "d"]
    arabic = reading.read_text("توكلت", "english")
    assert [s["value"] for s in arabic["segments"][0]["signs"]] == ["t", "w", "k", "l", "t"]
    assert reading.ethiopic_syllable("ማ") == "mā" and reading.ethiopic_syllable("ማ", amharic=True) == "ma"


def test_narration_is_speakable_and_tagged():
    lines = reading.narrate(reading.read_text("𓋹𓈖𓐍 𓄤𓆑𓂋", "english"), "english")
    text = " ".join(line["text"] for line in lines)
    assert "Word 1 is said ankh, and it means life." in text
    assert "the first sign gives the sounds a, n, kh" in text
    assert "ꜥ" not in text and "𓋹" not in text  # nothing a voice can't say
    assert {line["segment"] for line in lines if "Word 2" in line["text"]} == {1}
    sw = " ".join(line["text"] for line in reading.narrate(reading.read_text("𓋹𓈖𓐍", "swahili"), "swahili"))
    assert "Neno la 1 linatamkwa ankh, na maana yake ni uhai." in sw


# ------------------------------------------------------------------ tutor
def lesson_ctx(lang="english"):
    ctx = BrainContext(persona=get_persona("nefer").localized(lang))
    lesson_turn(ctx, "𓋹𓈖𓐍 𓄤𓆑𓂋")
    return ctx


def says(events):
    return [e for e in events if e["type"] == "say"]


def test_full_quiz_flow():
    ctx = lesson_ctx()
    start = says(lesson_turn(ctx, "quiz me"))
    assert start[0]["quiz"] == "start" and start[1]["segment"] == 0
    assert says(lesson_turn(ctx, "ankh"))[0]["correct"] is True
    assert says(lesson_turn(ctx, "it means life"))[0]["correct"] is True
    wrong = says(lesson_turn(ctx, "banana"))
    assert wrong[0]["correct"] is False and "starts with ne" in wrong[0]["text"]
    revealed = says(lesson_turn(ctx, "potato"))
    assert "It's said nefer" in revealed[0]["text"]
    assert "what does word 2 mean" in revealed[-1]["text"].lower()
    final = says(lesson_turn(ctx, "good"))
    assert final[-1]["quiz_done"] and "3 out of 4" in final[-1]["text"]
    assert ctx.quiz is None


def test_quiz_skip_stop_and_swahili():
    ctx = lesson_ctx("swahili")
    lesson_turn(ctx, "nijaribu")
    skipped = says(lesson_turn(ctx, "sijui"))
    assert "Linatamkwa ankh" in skipped[0]["text"]
    assert says(lesson_turn(ctx, "uhai"))[0]["correct"] is True
    done = says(lesson_turn(ctx, "acha"))
    assert done[-1]["quiz_done"] and ctx.quiz is None


def test_tutor_tolerates_speech_recognition():
    assert tutor.similar("nefir", "nefer") > 0.72
    assert tutor.similar("Ankh!", "ankh") == 1.0
    assert tutor.meaning_matches("I think it means life", ["life"])
    assert not tutor.meaning_matches("death", ["life"])


def test_lesson_commands():
    ctx = lesson_ctx()
    word = says(lesson_turn(ctx, "explain word 2"))
    assert word[0]["text"].startswith("Word 2 is said nefer") and word[0]["segment"] == 1
    again = lesson_turn(ctx, "read it again")
    assert again[0]["type"] == "reading"
    lesson_turn(ctx, "slower please")
    assert ctx.rate_scale == pytest.approx(0.85)
    assert lesson_turn(ctx, "translate water into Latin") is None  # normal tools still work mid-lesson


# ------------------------------------------------------------------ seeing
def test_model_reading_is_cross_checked():
    r = reading.reading_from_model(WALL, "english")
    statuses = [s["status"] for s in r["segments"]]
    assert statuses == ["confirmed", "disputed", "model_reading"]  # 𓄤 is nfr, not the model's ḥtp
    assert r["direction"] == "right_to_left" and r["segments"][0]["signs"]
    assert r["translation"]["english"] == "Life, an offering the king gives"


def test_see_without_any_vision_backend_is_honest():
    ctx = BrainContext(persona=get_persona("nefer"))
    events = collect(see(ctx, PNG, "", "upload"))
    assert len(events) == 1 and "can't see images yet" in events[0]["text"]
    assert collect(see(ctx, PNG, "", "live")) == [{"type": "live_unavailable"}]


def test_see_reads_and_teaches(monkeypatch):
    calls = with_vision_model(monkeypatch)
    ctx = BrainContext(persona=get_persona("nefer"))
    events = collect(see(ctx, PNG, "What does this wall say?", "camera"))
    assert events[0]["text"] == "Let me take a close look."
    assert events[1]["type"] == "reading" and ctx.lesson is events[1]["reading"]
    spoken = " ".join(e["text"] for e in events if e["type"] == "say")
    assert "read it from right to left" in spoken and "Word 1 is said ankh" in spoken
    assert "treat it as likely" in spoken  # unconfirmed words are flagged aloud
    content, instructions = calls[0]
    assert content[1]["type"] == "input_image" and "teacher" in instructions
    assert "What does this wall say?" not in content[0]["text"]  # a generic question is not passed on


def test_live_frames_skip_unchanged_scenes(monkeypatch):
    with_vision_model(monkeypatch)
    ctx = BrainContext(persona=get_persona("nefer"))
    first = collect(see(ctx, PNG, "", "live"))
    assert first[0]["type"] == "reading" and "word by word" in first[-1]["text"]
    assert collect(see(ctx, PNG, "", "live")) == [{"type": "live_unchanged"}]


def test_see_model_failure(monkeypatch):
    with_vision_model(monkeypatch, error=RuntimeError("HTTP 500"))
    events = collect(see(BrainContext(persona=get_persona("nefer")), PNG, "", "upload"))
    assert events[1]["type"] == "notice" and "HTTP 500" in events[1]["text"]
    assert "don't see any writing" in events[-1]["text"]


def test_warm_up():
    assert reading.warm_up()["total_seconds"] >= 0


# ------------------------------------------------------------------ session
def msg(name, payload=None):
    return json.dumps({"header": {"name": name, "request_id": "r"}, "payload": payload or {}})


def recv(ws):
    m = json.loads(ws.receive_text())
    return m["header"]["name"], m.get("payload") or {}


def init(ws, **payload):
    ws.send_text(msg("InitializeAvatarSession", {"persona": "nefer", **payload}))
    first = recv(ws)
    for _ in range(4):
        recv(ws)
    return first[1]


def until_end(ws):
    events = []
    while True:
        name, payload = recv(ws)
        events.append((name, payload))
        if name == "ChatSignal" and payload["type"] == "stream_end" and payload["stream_type"] == "avatar_text":
            return events


@pytest.fixture()
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_socket_photo_turn(client, monkeypatch):
    with_vision_model(monkeypatch)
    with client.websocket_connect("/ws/avatar") as ws:
        info = init(ws)
        assert info["vision"] == {"on_device_detector": False, "vision_model": True}
        ws.send_text(msg("SendHumanImage", {"image": PNG, "text": "What does this say?", "source": "upload"}))
        name, payload = recv(ws)
        assert name == "EchoHumanText" and payload["attachment"] == {"type": "image", "source": "upload"}
        events = until_end(ws)
        reading_msg = next(p for n, p in events if n == "AvatarReading")
        assert reading_msg["reading"]["segments"][0]["transliteration"] == "ꜥnḫ"
        word_lines = [p for n, p in events if n == "AvatarSpeech" and p.get("segment") == 0]
        assert word_lines and word_lines[0]["text"] == "Word 1 is said ankh, and it means life."
        ws.send_text(msg("SendHumanText", {"text": "quiz me", "end_of_speech": True}))
        recv(ws)
        quiz = [p for n, p in until_end(ws) if n == "AvatarSpeech" and p.get("text")]
        assert quiz[0]["quiz"] == "start" and quiz[1]["segment"] == 0


def test_socket_pasted_hieroglyphs_offline(client):
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SendHumanText", {"text": "Read this to me: 𓋹𓈖𓐍 𓄤𓆑𓂋", "end_of_speech": True}))
        recv(ws)
        events = until_end(ws)
        assert any(n == "AvatarReading" for n, _ in events)
        assert any(n == "AvatarSpeech" and p.get("segment") == 1 for n, p in events)


def test_socket_image_validation_and_no_vision(client):
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SendHumanImage", {"image": "not-an-image"}))
        assert recv(ws)[1]["code"] == "INVALID_MESSAGE"
        bad = "data:image/png;base64," + base64.b64encode(b"GIF89a....").decode()
        ws.send_text(msg("SendHumanImage", {"image": bad}))
        assert "do not match" in recv(ws)[1]["message"]
        ws.send_text(msg("SendHumanImage", {"image": PNG, "source": "upload"}))
        recv(ws)
        spoken = [p["text"] for n, p in until_end(ws) if n == "AvatarSpeech" and p.get("text")]
        assert "can't see images yet" in spoken[0]


def test_socket_live_frame_never_interrupts(client, monkeypatch):
    with_vision_model(monkeypatch)
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SendHumanImage", {"image": PNG, "source": "upload"}))
        ws.send_text(msg("SendHumanImage", {"image": PNG, "source": "live"}))
        names = []
        while True:
            name, payload = recv(ws)
            names.append((name, payload.get("status")))
            if name == "ChatSignal" and payload["type"] == "stream_end" and payload["stream_type"] == "avatar_text":
                break
        assert ("AvatarLiveStatus", "busy") in names
        assert "InterruptNotification" not in [n for n, _ in names]


def test_socket_language_switch_and_pace(client):
    with client.websocket_connect("/ws/avatar") as ws:
        init(ws)
        ws.send_text(msg("SetLanguage", {"language": "swahili"}))
        name, payload = recv(ws)
        assert name == "LanguageChanged" and payload["persona"]["language"] == "swahili"
        events = until_end(ws)
        speech = next(p for n, p in events if n == "AvatarSpeech")
        assert speech["voice"]["lang"] == "sw-KE" and speech["text"].startswith("Sawa")
        ws.send_text(msg("SendHumanText", {"text": "polepole", "end_of_speech": True}))
        recv(ws)
        slow = next(p for n, p in until_end(ws) if n == "AvatarSpeech" and p.get("text"))
        assert slow["voice"]["rate"] < 0.95
        # The learner's choice survives switching guides.
        ws.send_text(msg("SetPersona", {"persona": "theo"}))
        name, payload = recv(ws)
        assert payload["persona"]["id"] == "theo" and payload["language"] == "swahili"
        for _ in range(4):  # Theo's greeting
            recv(ws)
        ws.send_text(msg("SetLanguage", {"language": "klingon"}))
        name, payload = recv(ws)
        assert name == "Error" and payload["code"] == "INVALID_MESSAGE"


def test_fonts_are_served(client):
    css = client.get("/static/fonts/fonts.css")
    assert css.status_code == 200 and "unicode-range:U+13000-13455" in css.text
    font = client.get("/static/fonts/noto-sans-egyptian-hieroglyphs-egyptian-hieroglyphs-400-normal.woff2")
    assert font.status_code == 200 and font.content[:4] == b"wOF2"
