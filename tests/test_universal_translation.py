"""Regression checks for provider routing, formatting, and historical safeguards."""
from __future__ import annotations
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import universal_translation as mt

@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ESHB_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("ESHB_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ESHB_AI_PROVIDER", "disabled")
    monkeypatch.setenv("UNIVERSAL_MT_BASE_URL", "http://localhost:8001/v1")
    monkeypatch.setenv("UNIVERSAL_MT_MODEL", "tencent/Hy-MT2-1.8B")
    monkeypatch.delenv("GOOGLE_CLOUD_TRANSLATE_API_KEY", raising=False)

def run(**kw):
    return asyncio.run(mt.universal_translate(mt.UniversalTranslationRequest(**kw)))

def test_provider_capabilities_are_honest():
    c = mt.universal_capabilities()
    assert c["providers"]["hy-mt2"]["configured"]
    assert "sw" not in c["providers"]["hy-mt2"]["catalogue"]
    assert c["modalities"]["sign_language_video"].startswith("not_implemented")
    assert c["automatic_model_promotion"] is False
    assert mt._language_code("English") == "en"
    assert mt._language_code("Traditional Chinese") == "zh-Hant"
    with pytest.raises(mt.TranslationError, match="Unverified ancient"):
        mt._language_code("egyptian")
    with pytest.raises(mt.TranslationError, match="explicit source"):
        mt._choose_provider("hy-mt2", "auto", "en")
    with pytest.raises(mt.TranslationError, match="documented language"):
        mt._choose_provider("hy-mt2", "sw", "en")

def test_json_translates_only_visible_user_fields(monkeypatch):
    seen = []
    async def fake(text, source, target, request):
        seen.append(text)
        return "FR:" + text
    monkeypatch.setattr(mt, "_call_hy", fake)
    original = {"id":"NEVER", "title":"Welcome", "metadata":{"code":"X42", "caption":"Gallery"},
                "items":[{"label":"Start", "value":"UNCHANGED"}],
                "body":["First sentence", "Second sentence"], "count":12, "enabled":True}
    result = run(text=json.dumps(original),source_language="en",target_language="fr",format="json")
    translated = json.loads(result["translation"])
    assert translated["id"] == "NEVER" and translated["metadata"]["code"] == "X42"
    assert translated["items"][0]["value"] == "UNCHANGED"
    assert translated["body"] == ["FR:First sentence","FR:Second sentence"]
    assert translated["metadata"]["caption"] == "FR:Gallery"
    assert translated["count"] == 12 and translated["enabled"] is True
    assert result["segments"] == len(seen) == 5

def test_placeholders_markup_urls_and_integrity(monkeypatch):
    async def fake(text, source, target, request):
        return "Translated " + text
    monkeypatch.setattr(mt, "_call_hy", fake)
    source = "Hello {{username}}. Visit https://museum.example or <b>" + "$" + "{value}</b>."
    result = run(text=source,source_language="en",target_language="fr")
    for token in ("{{username}}","https://museum.example","<b>","</b>"):
        assert token in result["translation"]
    assert "$" + "{value}" in result["translation"]
    async def damaged(text, source, target, request):
        return text.replace("__GANPRESERVE_0000__", "")
    monkeypatch.setattr(mt, "_call_hy", damaged)
    with pytest.raises(mt.TranslationError,match="integrity"):
        run(text="Hello {{username}}",source_language="en",target_language="fr")

def test_glossary_fails_closed(monkeypatch):
    async def fake(text, source, target, request):
        return "Une partie magnifique"
    monkeypatch.setattr(mt,"_call_hy",fake)
    with pytest.raises(mt.TranslationError,match="terminology"):
        run(text="This heritage is great",source_language="en",target_language="fr",
            glossary={"heritage":"patrimoine"})

def test_srt_timestamps_preserved_and_invalid_rejected(monkeypatch):
    async def fake(text, source, target, request):
        return "TR:" + text
    monkeypatch.setattr(mt,"_call_hy",fake)
    source = ("1\n00:00:01,000 --> 00:00:03,500\nHello traveller!\n\n"
              "2\n00:00:04,000 --> 00:00:06,000\nWelcome home.\n")
    result=run(text=source,source_language="en",target_language="fr",format="srt")
    assert result["segments"] == 2
    assert "00:00:01,000 --> 00:00:03,500" in result["translation"]
    assert "00:00:04,000 --> 00:00:06,000" in result["translation"]
    assert "TR:Hello traveller!" in result["translation"]
    assert "TR:Welcome home." in result["translation"]
    with pytest.raises(mt.TranslationError,match="Invalid SRT"):
        run(text="Not subtitles",source_language="en",target_language="fr",format="srt")

def test_google_fallback_for_swahili(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_TRANSLATE_API_KEY", "not-a-real-key")
    async def fake(text, source, target, request):
        assert (source,target)==("en","sw")
        return "Habari"
    monkeypatch.setattr(mt,"_call_google",fake)
    result=run(text="Hello",source_language="en",target_language="sw")
    assert result["provider"] == "google-cloud" and result["translation"]=="Habari"

def test_missing_provider_is_explicit(monkeypatch):
    monkeypatch.delenv("UNIVERSAL_MT_BASE_URL")
    with pytest.raises(mt.TranslationError,match="No compatible"):
        run(text="Hello",source_language="en",target_language="fr")

def test_api_and_existing_egyptian_workflow(monkeypatch):
    async def fake(text, source, target, request):
        return "Bonjour"
    monkeypatch.setattr(mt,"_call_hy",fake)
    with TestClient(app) as client:
        assert client.get("/api/universal/capabilities").status_code == 200
        r=client.post("/api/universal/translate",json={
            "text":"Hello", "source_language":"en","target_language":"fr"})
        assert r.status_code == 200 and r.json()["translation"]=="Bonjour"
        ancient=client.post("/api/universal/translate",json={
            "text":"𓄤","source_language":"egyptian","target_language":"fr"})
        assert ancient.status_code == 422
        original=client.post("/api/egyptian/analyze-signs",json={"text":"𓄤"})
        assert original.status_code == 200 and original.json()["sign_count"]==1
