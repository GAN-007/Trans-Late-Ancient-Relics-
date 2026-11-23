"""Platform tools the guide can call: the AI is the learner's single point of contact with the whole app.

Each tool returns (output for the model, events for the learner's screen). Outputs
are compact JSON the language model reads; events are reading cards, translation
cards, spoken quiz lines or actions the browser performs (open the camera, read
the current camera view, switch tab). The same functions back the offline
responder, so behaviour does not depend on which model is connected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..ancient.bridge import MODERN_LANGUAGES, translate_any
from ..ancient.engine import LADDER_ORDER, LadderError
from ..ancient.grammar import REALIZERS
from . import reading as reading_mod
from . import tutor
from .personas import LANGUAGES

APP_TABS = {"translate", "ladder", "avatar", "lens", "talk", "learn", "dictionary", "script", "knowledge", "about"}


@dataclass
class ToolOutcome:
    output: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False}}


ANCIENT_IDS = [lang for lang in LADDER_ORDER if lang not in {"english", "swahili"}]

TOOL_SPECS: list[dict[str, Any]] = [
    _schema("translate_ancient",
            "Translate a short sentence or word between any languages and the ancient languages using the app's verified grammar engine. "
            "Covers Sumerian, Egyptian (hieroglyphic, Old, Middle), Old Latin, Old Arabic, Ge'ez, Old Amharic, Proto-Semitic and Proto-World, "
            "with English and Swahili directly and modern languages (French, German, Russian, Chinese, Hebrew, …) through machine translation via English. "
            "Handles statements, negation, yes/no questions and 'X is Y' sentences. Results include native scripts, an honest status "
            "(attested, composed, reconstructed, hypothetical, machine_translation) and a warning listing anything that was not translated.",
            {"text": {"type": "string", "description": "The sentence or word, in any supported language."},
             "source_language": {"type": "string", "description": "A ladder id (" + ", ".join(LADDER_ORDER) + ") or a modern language (" + ", ".join(MODERN_LANGUAGES) + ")."},
             "target_languages": {"type": "array", "items": {"type": "string"},
                                  "description": "Languages to translate into (same ids as source_language); ['all'] for every ancient rung."}},
            ["text", "source_language", "target_languages"]),
    _schema("read_script",
            "Read native-script ancient text (hieroglyphs, cuneiform, Ge'ez fidel, Old Italic, Safaitic, Arabic letters) as a lesson: "
            "script, direction, meaning, word-by-word pronunciation and sign functions. Shows a reading card and starts a lesson.",
            {"text": {"type": "string", "description": "The characters exactly as given."}}, ["text"]),
    _schema("translate_modern",
            "Translate text between modern languages (e.g. English, Swahili, French, German, Chinese, Russian) with the platform's "
            "machine-translation provider. If no provider is configured the result says so; then translate yourself and say it is your own translation.",
            {"text": {"type": "string"}, "source_language": {"type": "string", "description": "Language name or code, or 'auto'."},
             "target_language": {"type": "string", "description": "Language name or code."}},
            ["text", "source_language", "target_language"]),
    _schema("lookup_word",
            "Look up a word in the app's dictionaries (Middle Egyptian lexicon and the ancient-language concept lexicon) and across all ancient languages.",
            {"word": {"type": "string", "description": "An English/Swahili word, a transliteration, or native-script word."}}, ["word"]),
    _schema("teach_phrase",
            "Create a lesson card for a phrase in ANY language the learner is studying (French, Chinese, Russian, German, Arabic, Sumerian...). "
            "Give the words in reading order with an accurate pronunciation guide (pinyin for Chinese, romanization for Russian/Arabic/Japanese). "
            "The card lets the learner follow along and be quizzed. Only include words you are confident about.",
            {"language": {"type": "string", "description": "The language being taught, e.g. 'French'."},
             "phrase": {"type": "string", "description": "The phrase in its own script."},
             "translation": {"type": "string", "description": "The meaning in the learner's language."},
             "direction": {"type": "string", "enum": ["left_to_right", "right_to_left", "top_to_bottom"]},
             "words": {"type": "array", "maxItems": 20, "items": {"type": "object", "additionalProperties": False,
                       "properties": {"original": {"type": "string"}, "transliteration": {"type": "string"},
                                      "pronunciation": {"type": "string"}, "meaning": {"type": "string"}},
                       "required": ["original", "transliteration", "pronunciation", "meaning"]}}},
            ["language", "phrase", "translation", "direction", "words"]),
    _schema("start_quiz",
            "Start quizzing the learner on the current lesson (the last reading or taught phrase). The first question is spoken automatically; "
            "after calling this, say nothing more and wait for the learner's answer.", {}, []),
    _schema("app_action",
            "Do something in the app for the learner: open the camera, read what the camera sees now, start live reading, or open a tab.",
            {"action": {"type": "string", "enum": ["open_camera", "read_camera", "start_live_reading", "stop_live_reading", "open_tab"]},
             "tab": {"type": "string", "enum": sorted(APP_TABS), "description": "Only for open_tab."}},
            ["action"]),
    _schema("list_capabilities",
            "List the languages and features available in this app right now (which providers are configured).", {}, []),
]
TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}


def responses_tools() -> list[dict[str, Any]]:
    return [{"type": "function", **spec, "strict": False} for spec in TOOL_SPECS]


def chat_tools() -> list[dict[str, Any]]:
    return [{"type": "function", "function": spec} for spec in TOOL_SPECS]


# ------------------------------------------------------------------ implementations
def _ladder_rows(result: dict[str, Any], targets: list[str]) -> list[dict[str, Any]]:
    return [{"language": lang, "name": REALIZERS[lang].name if lang in REALIZERS else r.get("language_name", lang),
             "text": r["text"], "scripts": r["scripts"], "status": r["status"], "confidence": r["confidence"], "refusal": r.get("refusal"),
             "pronunciation": r.get("pronunciation")}
            for lang in targets if (r := result["results"].get(lang))]


async def translate_ancient(ctx: Any, text: str, source_language: str = "english", target_languages: list[str] | None = None) -> ToolOutcome:
    try:
        result = await translate_any(text, source_language, target_languages or ["all"])
    except LadderError as exc:
        return ToolOutcome({"ok": False, "error": str(exc)})
    if not result["ok"]:
        return ToolOutcome({"ok": False, "unknown_words": result["parse"]["unknown_words"], "message": result.get("message"),
                            "advice": "Tell the learner which words the grammar engine does not know; do not invent ancient forms."})
    rows = _ladder_rows(result, result["targets"])
    card = {"type": "ladder", "source": text, "source_language": result["source_language"], "rows": rows}
    if result.get("warning"):
        card["warning"] = result["warning"]
    slim = {r["language"]: {"text": r["text"], "say": (r.get("pronunciation") or {}).get("say", ""), "status": r["status"], "refusal": r["refusal"]}
            for r in rows}
    output: dict[str, Any] = {"ok": True, "meaning": result["meaning"], "translations": slim, "complete": result.get("complete", True),
                              "note": "Composed sentences are built by grammar rules, not quoted from ancient texts. A card with every script is already on screen."}
    if result.get("warning"):
        output["warning"] = result["warning"] + " Tell the learner plainly which part was not translated."
    if result.get("bridge"):
        output["bridge"] = result["bridge"]
    return ToolOutcome(output, [{"type": "card", "card": card}])


def read_script(ctx: Any, text: str) -> ToolOutcome:
    lesson = reading_mod.read_text(text, ctx.language if ctx else "english")
    if not lesson or not lesson["ok"]:
        return ToolOutcome({"ok": False, "message": "No supported ancient script found in that text."})
    if ctx is not None:
        ctx.lesson, ctx.quiz = lesson, None
    return ToolOutcome({"ok": True, "reading": json.loads(reading_mod.reading_summary(lesson).split(": ", 1)[1]),
                        "note": "A reading card is on screen and highlights words as you mention them. Walk the learner through it like a teacher."},
                       [{"type": "reading", "reading": lesson}])


async def translate_modern(ctx: Any, text: str, source_language: str = "auto", target_language: str = "english") -> ToolOutcome:
    from ..universal_translation import TranslationError, UniversalTranslationRequest, _provider_status, universal_translate
    if not any(p["configured"] for p in _provider_status().values()):
        return ToolOutcome({"ok": False, "available": False,
                            "instruction": "No machine-translation provider is configured. Translate it yourself and tell the learner it is your own translation."})
    try:
        result = await universal_translate(UniversalTranslationRequest(text=text[:4000], source_language=source_language or "auto",
                                                                       target_language=target_language))
    except TranslationError as exc:
        return ToolOutcome({"ok": False, "error": str(exc),
                            "instruction": "The provider could not do this pair. Translate it yourself and say it is your own translation."})
    card = {"type": "modern", "source": text, "rows": [{"language": result["target_language"], "name": target_language.title(),
                                                        "text": result["translation"], "scripts": {}, "status": "machine_translation",
                                                        "confidence": None}], "provider": result["provider"]}
    return ToolOutcome({"ok": True, "translation": result["translation"], "provider": result["provider"]}, [{"type": "card", "card": card}])


def lookup_word(ctx: Any, word: str) -> ToolOutcome:
    from ..egyptian import search_dictionary
    from .brain import tool_meaning
    from .personas import get_persona
    persona = ctx.persona if ctx is not None else get_persona(None)
    meaning = tool_meaning(word, persona)
    entries = search_dictionary(word, "all", None, 5)
    slim = [{k: e.get(k) for k in ("transliteration", "english", "swahili", "pos", "hieroglyphs", "confidence")} for e in entries]
    events = [{"type": "card", "card": meaning.card}] if meaning.card else []
    return ToolOutcome({"ok": True, "summary": meaning.summary, "middle_egyptian_dictionary": slim}, events)


def teach_phrase(ctx: Any, language: str, phrase: str, translation: str, direction: str = "left_to_right",
                 words: list[dict[str, str]] | None = None) -> ToolOutcome:
    learner = ctx.language if ctx else "english"
    segments = []
    for word in (words or [])[:20]:
        meaning = str(word.get("meaning") or "")
        segments.append({
            "original": str(word.get("original") or ""), "signs": [], "transliteration": str(word.get("transliteration") or ""),
            "pronunciation": str(word.get("pronunciation") or word.get("transliteration") or ""),
            "meaning": {"english": meaning, "swahili": meaning if learner == "swahili" else "", learner: meaning},
            "source": "guide (language model)", "status": "model_reading", "confidence": "medium",
        })
    if not segments:
        return ToolOutcome({"ok": False, "message": "A lesson needs at least one word."})
    lesson = {
        "ok": True, "source": "text", "original": phrase, "script": "modern", "language": language, "language_name": language,
        "script_name": language, "explain_language": learner, "direction": direction if direction in reading_mod.DIRECTION_WORDS["english"] else "left_to_right",
        "segments": segments, "translation": {"english": translation, learner: translation, "status": "model_reading"},
        "notes": ["Prepared by the guide's language model; check important details with a teacher or dictionary."],
        "coverage": {"confirmed_words": 0, "total_words": len(segments)}, "confidence": 0.6,
    }
    if ctx is not None:
        ctx.lesson, ctx.quiz = lesson, None
    return ToolOutcome({"ok": True, "words": len(segments),
                        "note": "The lesson card is on screen. Read the phrase aloud slowly, then explain it word by word; the learner can say 'quiz me'."},
                       [{"type": "reading", "reading": lesson}])


def start_quiz(ctx: Any) -> ToolOutcome:
    if ctx is None or not ctx.lesson:
        return ToolOutcome({"ok": False, "message": "There is no current lesson. Read or teach something first."})
    ctx.quiz, lines = tutor.start(ctx.lesson, ctx.language if ctx.language in {"english", "swahili"} else "english")
    if ctx.quiz is None:
        return ToolOutcome({"ok": False, "message": lines[0]["text"]})
    return ToolOutcome({"ok": True, "spoken_already": True, "instruction": "The first question has been asked aloud. Say nothing more now."},
                       [{"type": "say", **line} for line in lines])


def app_action(ctx: Any, action: str, tab: str | None = None) -> ToolOutcome:
    if action == "open_tab" and tab not in APP_TABS:
        return ToolOutcome({"ok": False, "error": f"Unknown tab. Use one of {sorted(APP_TABS)}."})
    event = {"type": "action", "action": action}
    if tab:
        event["tab"] = tab
    notes = {"open_camera": "The browser will ask the learner for camera permission if needed.",
             "read_camera": "The current camera view will be sent to you to read; tell the learner you're looking.",
             "start_live_reading": "Live reading reads new text as it comes into view."}
    return ToolOutcome({"ok": True, "done": action, "note": notes.get(action, "")}, [event])


def list_capabilities(ctx: Any) -> ToolOutcome:
    from ..universal_translation import _provider_status
    from .brain import _vision_backends, llm_status
    from .voice import tts_status
    local, model = _vision_backends()
    return ToolOutcome({
        "ancient_languages": ANCIENT_IDS,
        "learner_languages": {key: value["label"] for key, value in LANGUAGES.items()},
        "modern_translation_providers": {k: v["configured"] for k, v in _provider_status().items()},
        "vision": {"on_device_detector": local, "vision_model": model},
        "voice": tts_status()["provider"], "conversation_model": llm_status()["model"],
    })


SYNC_TOOLS = {"read_script": read_script, "lookup_word": lookup_word,
              "teach_phrase": teach_phrase, "start_quiz": start_quiz, "app_action": app_action, "list_capabilities": list_capabilities}


async def execute(ctx: Any, name: str, arguments: str | dict[str, Any]) -> ToolOutcome:
    """Run one tool call from the model. Bad calls return an error the model can recover from."""
    if name not in TOOL_NAMES:
        return ToolOutcome({"ok": False, "error": f"Unknown tool {name}."})
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
        if not isinstance(args, dict):
            raise ValueError
    except (ValueError, TypeError):
        return ToolOutcome({"ok": False, "error": "Arguments must be a JSON object."})
    try:
        if name == "translate_modern":
            return await translate_modern(ctx, **args)
        if name == "translate_ancient":
            return await translate_ancient(ctx, **args)
        return SYNC_TOOLS[name](ctx, **args)
    except TypeError as exc:
        return ToolOutcome({"ok": False, "error": f"Bad arguments for {name}: {exc}"})
    except Exception as exc:  # a tool failure must never end the conversation
        return ToolOutcome({"ok": False, "error": f"{name} failed: {exc}"})
