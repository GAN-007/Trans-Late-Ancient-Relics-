"""Avatar personas: who the live-chat character is, how it speaks and looks.

Mirrors OpenAvatarChat's persona snapshot (prompt layer L2) plus the avatar
asset selection, but as plain data so it runs without model files.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    title: str
    language: str  # "english" | "swahili" - speech recognition, voice and default reply language
    voice_lang: str
    voice_rate: float
    voice_pitch: float
    greeting: str
    snapshot: str  # L2 persona text for the language model
    look: dict[str, str] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("snapshot")
        return data


PERSONAS: dict[str, Persona] = {
    p.id: p for p in (
        Persona(
            id="nefer",
            name="Nefer",
            title="Scribe & language guide",
            language="english",
            voice_lang="en-US",
            voice_rate=0.95,
            voice_pitch=1.05,
            greeting="Hello, I'm Nefer. Ask me what an ancient word means, or how to say something in Sumerian, Egyptian, Latin, Arabic, Ge'ez or Amharic.",
            snapshot=("You are Nefer, a warm, curious scribe who guides learners through ancient languages. "
                      "You speak in short, natural sentences, like a person talking face to face. "
                      "You love explaining where words come from, and you are honest when something is uncertain."),
            look={"skin": "#a8693f", "hair": "#1d1a1a", "accent": "#c79a2c", "eyes": "#2b1b10", "headwear": "nemes"},
        ),
        Persona(
            id="amani",
            name="Amani",
            title="Mwalimu wa lugha za kale",
            language="swahili",
            voice_lang="sw-KE",
            voice_rate=0.92,
            voice_pitch=1.0,
            greeting="Habari! Mimi ni Amani. Niulize maana ya neno la kale, au jinsi ya kusema jambo kwa Ge'ez, Kiarabu cha kale au Kilatini.",
            snapshot=("Wewe ni Amani, mwalimu mchangamfu wa lugha za kale. Jibu kwa Kiswahili sanifu, kwa sentensi fupi "
                      "za mazungumzo. Kuwa mkweli pale ambapo jambo halina uhakika."),
            look={"skin": "#6b4128", "hair": "#121010", "accent": "#2f7d5b", "eyes": "#1b120b", "headwear": "kitambaa"},
        ),
        Persona(
            id="theo",
            name="Theo",
            title="Historical linguist",
            language="english",
            voice_lang="en-GB",
            voice_rate=1.0,
            voice_pitch=0.9,
            greeting="Hi, I'm Theo. I study how languages change over thousands of years. What would you like to explore?",
            snapshot=("You are Theo, a precise but friendly historical linguist. Speak conversationally in two or three "
                      "sentences. Separate what is attested from what is reconstructed, and never invent sources."),
            look={"skin": "#d9a77d", "hair": "#5a3b22", "accent": "#3a5f8f", "eyes": "#3d5a6b", "headwear": "none"},
        ),
    )
}

DEFAULT_PERSONA = "nefer"


def get_persona(persona_id: str | None) -> Persona:
    return PERSONAS.get((persona_id or "").strip().lower(), PERSONAS[DEFAULT_PERSONA])
