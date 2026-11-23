"""Avatar personas: who the live-chat character is, how it speaks and looks.

Mirrors OpenAvatarChat's persona snapshot (prompt layer L2) plus the avatar
asset selection, but as plain data so it runs without model files.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
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
    greetings: dict[str, str] = field(default_factory=dict)
    voices: dict[str, str] = field(default_factory=dict)
    neural_voice: str = "coral"  # OpenAI built-in voice used when server speech is enabled
    speaking_style: str = ""  # intonation guidance for expressive speech synthesis

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("snapshot")
        data.pop("greetings")
        data.pop("voices")
        data.pop("speaking_style")
        data.pop("neural_voice")
        return data

    def localized(self, language: str | None) -> "Persona":
        """The same character speaking the learner's chosen language."""
        language = language if language in LANGUAGES else self.language
        if language == self.language:
            return self
        greeting = self.greetings.get(language) or LANGUAGES[language]["hello"].format(name=self.name)
        return replace(self, language=language, voice_lang=self.voices.get(language, LANGUAGES[language]["voice"]),
                       greeting=greeting)


LANGUAGES: dict[str, dict[str, str]] = {
    # id: label (own name), BCP-47 code for speech recognition and browser voices, Azure neural voice,
    # hello (spoken greeting template; {name} is the guide's name). English and Kiswahili have full offline
    # teaching templates; the others are explained through the language model and translation providers.
    "english": {"label": "English", "voice": "en-US", "asr": "en-US", "azure": "en-US-JennyNeural", "mt": "en",
                "hello": "Hello, I'm {name}."},
    "swahili": {"label": "Kiswahili", "voice": "sw-KE", "asr": "sw-KE", "azure": "sw-KE-ZuriNeural", "mt": "sw",
                "hello": "Habari, mimi ni {name}."},
    "french": {"label": "Français", "voice": "fr-FR", "asr": "fr-FR", "azure": "fr-FR-DeniseNeural", "mt": "fr",
               "hello": "Bonjour, je suis {name}. Montrez-moi une écriture ancienne ou posez-moi une question sur une langue."},
    "german": {"label": "Deutsch", "voice": "de-DE", "asr": "de-DE", "azure": "de-DE-KatjaNeural", "mt": "de",
               "hello": "Hallo, ich bin {name}. Zeig mir eine alte Schrift oder frag mich etwas über eine Sprache."},
    "spanish": {"label": "Español", "voice": "es-ES", "asr": "es-ES", "azure": "es-ES-ElviraNeural", "mt": "es",
                "hello": "Hola, soy {name}. Muéstrame una escritura antigua o pregúntame sobre un idioma."},
    "portuguese": {"label": "Português", "voice": "pt-BR", "asr": "pt-BR", "azure": "pt-BR-FranciscaNeural", "mt": "pt",
                   "hello": "Olá, eu sou {name}. Mostre-me uma escrita antiga ou pergunte-me sobre um idioma."},
    "italian": {"label": "Italiano", "voice": "it-IT", "asr": "it-IT", "azure": "it-IT-ElsaNeural", "mt": "it",
                "hello": "Ciao, sono {name}. Mostrami una scrittura antica o chiedimi qualcosa su una lingua."},
    "russian": {"label": "Русский", "voice": "ru-RU", "asr": "ru-RU", "azure": "ru-RU-SvetlanaNeural", "mt": "ru",
                "hello": "Здравствуйте, я {name}. Покажите мне древнюю надпись или спросите меня о языке."},
    "chinese": {"label": "中文", "voice": "zh-CN", "asr": "zh-CN", "azure": "zh-CN-XiaoxiaoNeural", "mt": "zh",
                "hello": "你好，我是{name}。给我看古代文字，或者问我关于语言的问题。"},
    "japanese": {"label": "日本語", "voice": "ja-JP", "asr": "ja-JP", "azure": "ja-JP-NanamiNeural", "mt": "ja",
                 "hello": "こんにちは、{name}です。古代の文字を見せるか、言語について質問してください。"},
    "arabic": {"label": "العربية", "voice": "ar-SA", "asr": "ar-SA", "azure": "ar-SA-ZariyahNeural", "mt": "ar",
               "hello": "مرحباً، أنا {name}. أرني كتابة قديمة أو اسألني عن لغة."},
    "hindi": {"label": "हिन्दी", "voice": "hi-IN", "asr": "hi-IN", "azure": "hi-IN-SwaraNeural", "mt": "hi",
              "hello": "नमस्ते, मैं {name} हूँ। मुझे कोई प्राचीन लिपि दिखाइए या किसी भाषा के बारे में पूछिए।"},
    "amharic": {"label": "አማርኛ", "voice": "am-ET", "asr": "am-ET", "azure": "am-ET-MekdesNeural", "mt": "am",
                "hello": "ሰላም፣ እኔ {name} ነኝ። የጥንት ጽሑፍ አሳዩኝ ወይም ስለ ቋንቋ ጠይቁኝ።"},
}
FULL_OFFLINE_LANGUAGES = {"english", "swahili"}


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
            greeting="Hello, I'm Nefer. Show me ancient writing with your camera or a photo and I'll read it to you, or ask me how to say something in Sumerian, Egyptian, Latin, Arabic, Ge'ez or Amharic.",
            snapshot=("You are Nefer, a warm, curious scribe who guides learners through ancient languages. "
                      "You speak in short, natural sentences, like a person talking face to face. "
                      "You love explaining where words come from, and you are honest when something is uncertain."),
            look={"skin": "#a8693f", "hair": "#1d1a1a", "accent": "#c79a2c", "eyes": "#2b1b10", "headwear": "nemes"},
            greetings={"swahili": "Habari, mimi ni Nefer. Nionyeshe maandishi ya kale kwa kamera au picha, nami nitakusomea na kukufundisha kuyasoma."},
            voices={"swahili": "sw-KE"},
            neural_voice="coral",
            speaking_style="A warm, curious teacher. Smile in the voice, slow down and articulate clearly when pronouncing ancient words, sound genuinely pleased when the learner gets something right.",
        ),
        Persona(
            id="amani",
            name="Amani",
            title="Mwalimu wa lugha za kale",
            language="swahili",
            voice_lang="sw-KE",
            voice_rate=0.92,
            voice_pitch=1.0,
            greeting="Habari! Mimi ni Amani. Nionyeshe maandishi ya kale kwa kamera au picha nikusomee, au niulize jinsi ya kusema jambo kwa Ge'ez, Kiarabu cha kale au Kilatini.",
            snapshot=("Wewe ni Amani, mwalimu mchangamfu wa lugha za kale. Jibu kwa Kiswahili sanifu, kwa sentensi fupi "
                      "za mazungumzo. Kuwa mkweli pale ambapo jambo halina uhakika."),
            look={"skin": "#6b4128", "hair": "#121010", "accent": "#2f7d5b", "eyes": "#1b120b", "headwear": "kitambaa"},
            greetings={"english": "Hello, I'm Amani. Show me ancient writing with your camera or a photo, and I'll read it to you and teach you to read it."},
            voices={"english": "en-KE"},
            neural_voice="sage",
            speaking_style="A calm, encouraging East African teacher. Patient and kind, clear pronunciation, gentle warmth when correcting.",
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
            greetings={"swahili": "Habari, mimi ni Theo. Ninachunguza jinsi lugha zinavyobadilika kwa maelfu ya miaka. Ungependa tuchunguze nini?"},
            voices={"swahili": "sw-KE"},
            neural_voice="ash",
            speaking_style="A thoughtful, precise lecturer with dry good humour. Measured pace, emphasis on key terms.",
        ),
    )
}

DEFAULT_PERSONA = "nefer"


def get_persona(persona_id: str | None) -> Persona:
    return PERSONAS.get((persona_id or "").strip().lower(), PERSONAS[DEFAULT_PERSONA])
