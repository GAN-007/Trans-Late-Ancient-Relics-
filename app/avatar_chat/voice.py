"""Natural speech for the guide: server-side neural text-to-speech.

Providers (ESHB_TTS_PROVIDER):
  browser  - default; the browser's own voice (no cost, quality varies by device)
  openai   - OpenAI /audio/speech; the model follows spoken-style instructions, so the
             guide's personality and the moment (praise, gentle correction, slow
             pronunciation) are heard in the intonation
  azure    - Azure AI Speech neural voices via SSML, including Kenyan Swahili voices

The audio goes to the browser, which plays it and drives the face from the real
waveform, so the lips follow the actual voice.
"""
from __future__ import annotations

import base64
import hashlib
import os
from collections import OrderedDict
from typing import Any
from xml.sax.saxutils import escape

import httpx

from .personas import LANGUAGES, Persona

EMOTION_STYLE = {
    "happy": "Sound delighted and proud of the learner.",
    "encouraging": "Be gentle and reassuring; the learner made a mistake and should feel safe to try again.",
    "teaching": "Speak slowly and articulate each ancient word clearly, with a short pause before it.",
    "curious": "Sound interested and engaged.",
    "warm": "Sound warm and welcoming.",
    "neutral": "",
}
AZURE_STYLE = {"happy": "cheerful", "encouraging": "gentle", "teaching": "calm", "warm": "friendly", "curious": "friendly"}

DEFAULT_TRANSPORT: httpx.AsyncBaseTransport | None = None  # test hook

_CACHE: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()
_CACHE_LIMIT = 256


def tts_status() -> dict[str, Any]:
    provider = os.environ.get("ESHB_TTS_PROVIDER", "browser").strip().lower()
    if provider == "openai":
        configured = bool(os.environ.get("ESHB_TTS_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        model = os.environ.get("ESHB_TTS_MODEL", "gpt-4o-mini-tts")
    elif provider == "azure":
        configured = bool(os.environ.get("AZURE_SPEECH_KEY") and (os.environ.get("AZURE_SPEECH_REGION") or os.environ.get("AZURE_SPEECH_ENDPOINT")))
        model = "azure-neural"
    else:
        provider, configured, model = "browser", True, None
    if not configured:
        provider, model = "browser", None
    return {"provider": provider, "model": model, "server_audio": provider != "browser"}


def _cache_key(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()


async def _openai(text: str, persona: Persona, language: str, emotion: str, rate: float) -> tuple[bytes, str]:
    base = (os.environ.get("ESHB_TTS_BASE_URL") or os.environ.get("ESHB_AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("ESHB_TTS_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("ESHB_TTS_MODEL", "gpt-4o-mini-tts")
    body: dict[str, Any] = {"model": model, "input": text[:4000], "voice": os.environ.get("ESHB_TTS_VOICE") or persona.neural_voice,
                            "response_format": "mp3", "speed": max(0.5, min(1.5, rate / 0.95))}
    if not model.startswith("tts-1"):
        label = LANGUAGES.get(language, LANGUAGES["english"])["label"]
        body["instructions"] = " ".join(x for x in (
            persona.speaking_style, EMOTION_STYLE.get(emotion, ""),
            f"Speak {label} naturally{' with a Kenyan accent' if language in {'swahili', 'english'} and persona.id == 'amani' else ''}.",
            "Pronounce transliterated ancient words carefully, syllable by syllable.") if x)[:4000]
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), transport=DEFAULT_TRANSPORT) as client:
        response = await client.post(f"{base}/audio/speech", headers={"Authorization": f"Bearer {key}"}, json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"Speech provider returned HTTP {response.status_code}")
        return response.content, "audio/mpeg"


async def _azure(text: str, persona: Persona, language: str, emotion: str, rate: float) -> tuple[bytes, str]:
    endpoint = os.environ.get("AZURE_SPEECH_ENDPOINT") or f"https://{os.environ['AZURE_SPEECH_REGION']}.tts.speech.microsoft.com/cognitiveservices/v1"
    info = LANGUAGES.get(language, LANGUAGES["english"])
    voice = os.environ.get(f"ESHB_AZURE_VOICE_{language.upper()}") or info["azure"]
    if persona.id == "theo" and language == "english":
        voice = os.environ.get("ESHB_AZURE_VOICE_THEO", "en-GB-RyanNeural")
    lang_code = "-".join(voice.split("-")[:2])
    percent = round((rate / 0.95 - 1) * 100)
    inner = f'<prosody rate="{percent:+d}%">{escape(text[:3000])}</prosody>'
    style = AZURE_STYLE.get(emotion)
    if style and lang_code.startswith(("en-US", "zh-CN")):  # expressive styles exist only for some voices
        inner = f'<mstts:express-as style="{style}">{inner}</mstts:express-as>'
    ssml = (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xmlns:mstts='https://www.w3.org/2001/mstts' "
            f"xml:lang='{lang_code}'><voice name='{voice}'>{inner}</voice></speak>")
    headers = {"Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"], "Content-Type": "application/ssml+xml",
               "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "TransLateAncientRelics"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0), transport=DEFAULT_TRANSPORT) as client:
        response = await client.post(endpoint, headers=headers, content=ssml.encode("utf-8"))
        if response.status_code >= 400:
            raise RuntimeError(f"Azure speech returned HTTP {response.status_code}")
        return response.content, "audio/mpeg"


async def synthesize(text: str, persona: Persona, language: str, emotion: str = "neutral", rate: float = 0.95) -> dict[str, str] | None:
    """Return {'audio': base64, 'mime': ...} or None when the browser voice should be used."""
    status = tts_status()
    if not status["server_audio"] or not text.strip():
        return None
    key = _cache_key(status["provider"], status["model"], persona.id, persona.neural_voice, language, emotion, round(rate, 2), text)
    if key in _CACHE:
        _CACHE.move_to_end(key)
        audio, mime = _CACHE[key]
    else:
        audio, mime = await (_openai if status["provider"] == "openai" else _azure)(text, persona, language, emotion, rate)
        _CACHE[key] = (audio, mime)
        if len(_CACHE) > _CACHE_LIMIT:
            _CACHE.popitem(last=False)
    return {"audio": base64.b64encode(audio).decode("ascii"), "mime": mime}


def emotion_for(text: str, event: dict[str, Any] | None = None) -> str:
    """Pick the guide's emotional colour for a sentence (drives voice style and facial expression)."""
    event = event or {}
    if event.get("correct") is True:
        return "happy"
    if event.get("correct") is False:
        return "encouraging"
    if event.get("segment") is not None:
        return "teaching"
    lowered = text.lower()
    if any(w in lowered for w in ("well done", "perfect", "great", "excellent", "hongera", "safi", "vizuri", "bravo", "très bien")):
        return "happy"
    if text.rstrip().endswith("?"):
        return "curious"
    if any(w in lowered for w in ("hello", "habari", "welcome", "karibu", "bonjour", "hola")):
        return "warm"
    return "neutral"
