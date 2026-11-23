"""The avatar's mind: grounding tools, a layered prompt and a streaming language model.

Follows OpenAvatarChat's agent design:
  - tools run first and their verified output is injected into the prompt,
  - the prompt is compiled in four layers (L1 core rules, L2 persona snapshot,
    L3 environment state, L4 dialogue) like handlers/agent/prompt/prompt_compiler.py,
  - the reply streams token by token so speech can start before it finishes,
    as in handlers/llm/openai_compatible.

With no language model configured, a deterministic responder answers from the
same tools, so the live chat still works fully offline.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..ancient.engine import LADDER_ORDER, LadderError, concept_table, translate as ladder_translate
from ..ancient.grammar import REALIZERS
from ..ancient.lexicon import english_index
from ..ancient.parsing import parse
from . import reading as reading_mod
from . import tutor
from .personas import FULL_OFFLINE_LANGUAGES, LANGUAGES, Persona

# ------------------------------------------------------------------ language names
LANGUAGE_WORDS: dict[str, str] = {
    "sumerian": "archaic_sumerian", "kisumeri": "archaic_sumerian", "cuneiform": "archaic_sumerian",
    "egyptian": "old_egyptian", "old egyptian": "old_egyptian", "kimisri": "old_egyptian", "hieroglyphs": "old_egyptian",
    "hieroglyphics": "old_egyptian", "hieroglyphic": "old_egyptian", "middle egyptian": "middle_egyptian",
    "latin": "old_latin", "old latin": "old_latin", "kilatini": "old_latin",
    "arabic": "old_arabic", "old arabic": "old_arabic", "kiarabu": "old_arabic",
    "ge'ez": "geez", "geez": "geez", "ge’ez": "geez", "kigeez": "geez", "kige'ez": "geez", "ethiopic": "geez",
    "amharic": "old_amharic", "old amharic": "old_amharic", "kiamhari": "old_amharic",
    "proto-semitic": "proto_semitic", "proto semitic": "proto_semitic",
    "proto-world": "proto_world", "proto world": "proto_world",
    "swahili": "swahili", "kiswahili": "swahili", "english": "english", "kiingereza": "english",
    "every language": "all", "all languages": "all", "lugha zote": "all",
}
_LANG_ALT = "|".join(sorted((re.escape(k) for k in LANGUAGE_WORDS), key=len, reverse=True))

TRANSLATE_PATTERNS = [
    re.compile(rf"\b(?:translate|say|write)\s+[\"“'‘]?(?P<text>.+?)[\"”'’]?\s+(?:in|into|to)\s+(?P<lang>{_LANG_ALT})\b", re.I),
    re.compile(rf"\bhow\s+(?:do|would|can)\s+(?:you|i|we)\s+(?:say|write)\s+[\"“'‘]?(?P<text>.+?)[\"”'’]?\s+in\s+(?P<lang>{_LANG_ALT})\b", re.I),
    re.compile(rf"\bwhat\s+is\s+[\"“'‘]?(?P<text>.+?)[\"”'’]?\s+in\s+(?P<lang>{_LANG_ALT})\b", re.I),
    re.compile(rf"\btafsiri\s+[\"“'‘]?(?P<text>.+?)[\"”'’]?\s+(?:kwa|kwenda|kuwa)\s+(?P<lang>{_LANG_ALT})\b", re.I),
    re.compile(rf"\b(?:unasemaje|tunasemaje|husemwaje)\s+[\"“'‘]?(?P<text>.+?)[\"”'’]?\s+kwa\s+(?P<lang>{_LANG_ALT})\b", re.I),
]
MEANING_PATTERNS = [
    re.compile(r"\bwhat\s+does\s+[\"“'‘]?(?P<word>[^\s\"”'’?]+(?:\s[^\s\"”'’?]+)?)[\"”'’]?\s+mean\b", re.I),
    re.compile(r"\b(?:meaning|translation)\s+of\s+[\"“'‘]?(?P<word>[^\s\"”'’?]+)", re.I),
    re.compile(r"\bmaana\s+ya\s+[\"“'‘]?(?P<word>[^\s\"”'’?]+)", re.I),
    re.compile(r"[\"“'‘]?(?P<word>[^\s\"”'’?]+)[\"”'’]?\s+(?:ina\s+)?maana\s+(?:yake\s+)?(?:ni\s+)?(?:nini|gani)", re.I),
]
LANGUAGE_LIST = re.compile(r"\b(?:what|which)\s+languages\b|\blugha\s+(?:gani|zipi)\b|\bwhich\s+scripts\b", re.I)
GREETING = re.compile(r"^\s*(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|habari|hujambo|jambo|mambo|salaam|salam)\b", re.I)
IDENTITY = re.compile(r"\b(?:who\s+are\s+you|your\s+name|wewe\s+ni\s+nani|jina\s+lako)\b", re.I)
HELP = re.compile(r"\b(?:help|what\s+can\s+you\s+do|unaweza\s+kufanya\s+nini|nisaidie)\b", re.I)

LANG_LABEL = {lang: REALIZERS[lang].name for lang in REALIZERS}
LANG_LABEL_SW = {
    "english": "Kiingereza", "swahili": "Kiswahili", "archaic_sumerian": "Kisumeri cha kale",
    "old_latin": "Kilatini cha kale", "old_arabic": "Kiarabu cha kale", "geez": "Ge'ez",
    "old_amharic": "Kiamhari cha kale", "proto_semitic": "Proto-Semitic", "proto_world": "Proto-World",
    "archaic_hieroglyphic": "Hieroglifu za awali", "old_egyptian": "Kimisri cha kale", "middle_egyptian": "Kimisri cha kati",
}
SPOKEN_HIGHLIGHTS = ["old_egyptian", "archaic_sumerian", "old_latin", "geez"]
# Test hook: an httpx transport used for every model call when no transport is passed.
DEFAULT_TRANSPORT: httpx.AsyncBaseTransport | None = None


@dataclass
class ToolResult:
    name: str
    data: dict[str, Any]
    summary: str  # compact fact sheet for the language model (prompt layer L3)
    reply: str  # the offline spoken answer
    card: dict[str, Any] | None = None


@dataclass
class Turn:
    role: str  # "user" | "assistant"
    text: str


@dataclass
class BrainContext:
    persona: Persona
    history: list[Turn] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)
    max_history: int = 20
    lesson: dict[str, Any] | None = None  # the reading currently being taught
    quiz: tutor.Quiz | None = None
    rate_scale: float = 1.0  # learner can ask the guide to speak slower or faster
    live_signature: str = ""  # last live-camera reading, so an unchanged scene is not re-read
    language_notice_given: bool = False

    @property
    def language(self) -> str:
        return self.persona.language

    def remember(self, role: str, text: str) -> None:
        if text.strip():
            self.history.append(Turn(role, text.strip()))
            del self.history[:-self.max_history]


# ------------------------------------------------------------------ tools
def _sw(persona: Persona) -> bool:
    return persona.language == "swahili"


def _label(lang: str, persona: Persona) -> str:
    return (LANG_LABEL_SW if _sw(persona) else LANG_LABEL).get(lang, lang)


def _clean_phrase(text: str) -> str:
    return text.strip().strip("\"“”'‘’.,!?").strip()


def _ladder(text: str, persona: Persona) -> dict[str, Any] | None:
    sources = ["swahili", "english"] if _sw(persona) else ["english", "swahili"]
    for source in sources:
        try:
            result = ladder_translate(text, source)
        except LadderError:
            continue
        if result["ok"]:
            return result
    return None


def _card(result: dict[str, Any], targets: list[str]) -> dict[str, Any]:
    return {
        "type": "ladder",
        "source": result["source"],
        "source_language": result["source_language"],
        "rows": [
            {"language": lang, "name": REALIZERS[lang].name, "text": r["text"], "scripts": r["scripts"],
             "status": r["status"], "confidence": r["confidence"], "refusal": r.get("refusal")}
            for lang in targets if (r := result["results"].get(lang))
        ],
    }


def tool_translate(text: str, target: str, persona: Persona) -> ToolResult | None:
    phrase = _clean_phrase(text)
    result = _ladder(phrase, persona)
    sw = _sw(persona)
    if result is None:
        reply = (f"Sijaweza kuelewa \"{phrase}\" bado. Jaribu sentensi rahisi kama \"Mfalme alipenda mama\"."
                 if sw else
                 f"I couldn't map \"{phrase}\" to a meaning I know yet. Try a simple sentence like \"The king loved the good mother\".")
        return ToolResult("translate", {"ok": False, "text": phrase}, f"Translation of '{phrase}' failed: not in the ladder lexicon.", reply)
    targets = [lang for lang in LADDER_ORDER if lang != result["source_language"]] if target == "all" else [target]
    rows = {lang: result["results"][lang] for lang in targets if lang in result["results"]}
    spoken: list[str] = []
    for lang in (SPOKEN_HIGHLIGHTS if target == "all" else targets):
        r = rows.get(lang)
        if not r:
            continue
        if r.get("refusal") or not r["text"]:
            spoken.append((f"{_label(lang, persona)} haikuandika sentensi kama hii." if sw
                           else f"{_label(lang, persona)} didn't write sentences like this, so there's no honest form."))
            continue
        spoken.append(f"{'Kwa' if sw else 'In'} {_label(lang, persona)}, {'ni' if sw else 'it is'} {r['text']}.")
    composed = any(r["status"] in {"composed", "reconstructed_composition"} for r in rows.values())
    if composed:
        spoken.append("Sentensi hizi zimejengwa kwa kanuni za sarufi, si nukuu za maandishi ya kale." if sw
                      else "These sentences are built from grammar rules, not quoted from ancient texts.")
    if target == "all":
        spoken.append("Nimeweka lugha zote kwenye kadi." if sw else "I've put every language on the card.")
    facts = {lang: {"text": r["text"], "scripts": r["scripts"], "status": r["status"], "refusal": r.get("refusal")} for lang, r in rows.items()}
    summary = (f"Verified ladder translation of '{phrase}' (meaning {json.dumps(result['meaning'], ensure_ascii=False)}): "
               f"{json.dumps(facts, ensure_ascii=False)}")
    return ToolResult("translate", {"ok": True, "result": result, "targets": targets}, summary, " ".join(spoken), _card(result, targets))


def _english_concept(word: str) -> tuple[str, str] | None:
    hits = english_index().get(word.lower())
    if hits:
        kind, concept, _ = hits[0]
        return kind, concept
    return None


def tool_meaning(word: str, persona: Persona) -> ToolResult:
    word = _clean_phrase(word)
    sw = _sw(persona)
    found: list[tuple[str, dict[str, Any]]] = []
    for lang in LADDER_ORDER:
        if lang in {"english", "proto_world"}:
            continue
        parsed = parse(word, lang)
        frame = parsed.get("frame")
        if frame and frame.get("kind") == "word" and not parsed["unknown"]:
            found.append((lang, frame))
    if not found:
        direct = _english_concept(word)
        if direct:
            table = concept_table(direct[1])
            rows = [lang for lang in LADDER_ORDER if lang != "english" and table["results"][lang]["ok"]]
            spoken = " ".join(f"{'Kwa' if sw else 'In'} {_label(lang, persona)}, {table['results'][lang]['text']}." for lang in SPOKEN_HIGHLIGHTS if lang in rows)
            reply = (f"\"{word}\" kwa lugha za kale: {spoken}" if sw else f"Here's \"{word}\" across the ancient languages. {spoken}")
            card = {"type": "concept", "concept": direct[1], "rows": [
                {"language": lang, "name": REALIZERS[lang].name, "text": table["results"][lang]["text"],
                 "scripts": table["results"][lang]["scripts"], "status": table["results"][lang]["status"],
                 "confidence": table["results"][lang]["confidence"]} for lang in rows]}
            return ToolResult("meaning", {"concept": direct[1]}, f"Concept '{direct[1]}' forms: {json.dumps(card['rows'], ensure_ascii=False)}", reply, card)
        from ..egyptian import current_lexicon
        key = unicodedata.normalize("NFC", word.lower())
        entry = next((e for e in current_lexicon() if e["transliteration"].lower() == key), None)
        if entry:
            meaning = ", ".join(entry["swahili" if sw else "english"][:3])
            reply = (f"Kwa Kimisri cha kati, {word} maana yake ni {meaning}." if sw else f"In Middle Egyptian, {word} means {meaning}.")
            return ToolResult("meaning", {"lexicon": entry}, f"Middle Egyptian lexicon: {json.dumps(entry, ensure_ascii=False)}", reply)
        reply = (f"Sijapata \"{word}\" kwenye kamusi yangu ya lugha za kale." if sw
                 else f"I don't have \"{word}\" in my ancient-language lexicon yet, so I won't guess.")
        return ToolResult("meaning", {"found": False}, f"'{word}' is not in any lexicon; say so rather than guessing.", reply)
    lang, frame = found[0]
    gloss_frame = frame
    english = REALIZERS["english"].realize(gloss_frame)["text"]
    swahili = REALIZERS["swahili"].realize(gloss_frame)["text"]
    others = ", ".join(_label(other, persona) for other, f in found[1:] if f == frame)
    status = REALIZERS[lang].status
    if sw:
        reply = f"{word} ni {_label(lang, persona)}, maana yake ni \"{swahili}\"."
        if status == "reconstructed":
            reply += " Ni neno lililokisiwa, halikuandikwa kamwe."
    else:
        reply = f"{word} is {_label(lang, persona)} for \"{english}\"."
        if status == "reconstructed":
            reply += " It's a reconstruction; nobody ever wrote it down."
        if others:
            reply += f" The same spelling also works in {others}."
    return ToolResult("meaning", {"language": lang, "frame": frame},
                      f"'{word}' parsed as {lang} {json.dumps(frame)} = English '{english}', Swahili '{swahili}'.", reply)


def tool_languages(persona: Persona) -> ToolResult:
    names = [_label(lang, persona) for lang in LADDER_ORDER if lang not in {"english", "swahili"}]
    if _sw(persona):
        reply = "Ninaweza kutafsiri kati ya Kiingereza, Kiswahili na " + ", ".join(names[:-1]) + " na " + names[-1] + "."
    else:
        reply = "I can translate between English, Swahili and " + ", ".join(names[:-1]) + ", and " + names[-1] + "."
    return ToolResult("languages", {"languages": LADDER_ORDER}, "Supported: " + ", ".join(LADDER_ORDER), reply)


def run_tools(text: str, persona: Persona) -> list[ToolResult]:
    for pattern in TRANSLATE_PATTERNS:
        m = pattern.search(text)
        if m:
            target = LANGUAGE_WORDS[m.group("lang").lower()]
            result = tool_translate(m.group("text"), target, persona)
            return [result] if result else []
    for pattern in MEANING_PATTERNS:
        m = pattern.search(text)
        if m:
            return [tool_meaning(m.group("word"), persona)]
    if LANGUAGE_LIST.search(text):
        return [tool_languages(persona)]
    return []


def offline_reply(text: str, persona: Persona, tools: list[ToolResult]) -> str:
    if tools:
        return " ".join(t.reply for t in tools)
    sw = _sw(persona)
    if IDENTITY.search(text):
        return persona.greeting
    if GREETING.search(text):
        return ("Habari! Niko tayari. Niulize neno au sentensi ya kutafsiri." if sw
                else "Hello! It's good to talk with you. What would you like to translate or learn today?")
    if HELP.search(text):
        return ("Unaweza kusema, kwa mfano: tafsiri \"mfalme alipenda mama\" kwa Kilatini, au maana ya lugal ni nini." if sw
                else "You can say things like: translate \"the king made a great house\" into Sumerian, what does lugal mean, or which languages do you know.")
    # A bare sentence: try it on the whole ladder.
    result = tool_translate(text, "all", persona) if len(text) <= 200 else None
    if result and result.data.get("ok"):
        tools.append(result)
        return result.reply
    return ("Sina akili bandia iliyounganishwa sasa hivi, kwa hiyo ninajibu kutafsiri na maana za maneno tu. Jaribu: tafsiri \"maji\" kwa Ge'ez." if sw
            else "No language model is connected right now, so I can only answer translations and word meanings. Try: translate \"water\" into Ge'ez.")


# ------------------------------------------------------------------ prompt compiler (4 layers)
L1_CORE = """You are a live, talking avatar inside a translation and language-learning app: the learner's teacher and their way into everything the app can do.
Everything you write is spoken aloud by text-to-speech and lip-synced to your face, so talk like a person, not a document.
You have tools for the whole platform: verified ancient-language translation, reading native scripts as lessons, modern translation,
dictionaries, lesson cards for any language, quizzes, and app actions (open the camera, read what the camera sees, switch tabs).
Use them instead of guessing. Teach the way a good teacher does: one idea at a time, check understanding, encourage, and invite practice.
Rules:
- Reply in one to three short, natural spoken sentences. No markdown, lists, tables, emojis or code.
- Reply in the learner's chosen language (given below) unless they ask for another; when teaching a language, give its words in that language with pronunciation.
- When <environment-state> contains verified translations or word facts, use exactly those forms and never invent other ancient forms.
- If a form is composed, reconstructed or hypothetical, say so briefly. If you do not know, say so.
- The app shows a card with every script; you do not need to read cuneiform, hieroglyphs or fidel letter by letter."""


def compile_prompt(ctx: BrainContext, user_text: str, tools: list[ToolResult]) -> tuple[str, list[dict[str, str]]]:
    env = {k: v for k, v in ctx.environment.items() if v}
    state_lines = [t.summary for t in tools]
    if ctx.lesson:
        state_lines.append(reading_mod.reading_summary(ctx.lesson))
    state_lines.append(f"The learner's chosen language is {LANGUAGES[ctx.language]['label']}; reply in it.")
    if env:
        state_lines.append("App context: " + json.dumps(env, ensure_ascii=False)[:1500])
    system = L1_CORE + "\n\n[Persona]\n" + ctx.persona.snapshot
    if state_lines:
        system += "\n\n<environment-state>\n" + "\n".join(state_lines)[:6000] + "\n</environment-state>"
    messages = [{"role": t.role, "content": t.text} for t in ctx.history]
    messages.append({"role": "user", "content": user_text})
    return system, messages


# ------------------------------------------------------------------ language model
def llm_status() -> dict[str, Any]:
    provider = os.environ.get("ESHB_AI_PROVIDER", "openai" if os.environ.get("OPENAI_API_KEY") else "disabled").strip().lower()
    api = os.environ.get("ESHB_AVATAR_LLM_API", "responses").strip().lower()
    key = os.environ.get("ESHB_AVATAR_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base = os.environ.get("ESHB_AVATAR_LLM_BASE_URL") or os.environ.get("ESHB_AI_BASE_URL") or "https://api.openai.com/v1"
    local = base.startswith(("http://127.0.0.1", "http://localhost"))
    configured = provider != "disabled" and (bool(key) or local)
    return {
        "configured": configured,
        "api": "chat_completions" if api in {"chat", "chat_completions", "openai_compatible"} else "responses",
        "model": (os.environ.get("ESHB_AVATAR_LLM_MODEL") or os.environ.get("ESHB_AI_MODEL", "gpt-5.6")) if configured else None,
        "base_url": base.rstrip("/"),
        "offline_fallback": True,
    }


async def stream_llm(system: str, messages: list[dict[str, str]], transport: httpx.AsyncBaseTransport | None = None) -> AsyncIterator[str]:
    status = llm_status()
    key = os.environ.get("ESHB_AVATAR_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    timeout = httpx.Timeout(float(os.environ.get("ESHB_AVATAR_LLM_TIMEOUT_SECONDS", "45")), connect=10.0)
    if status["api"] == "chat_completions":
        url = f"{status['base_url']}/chat/completions"
        body: dict[str, Any] = {"model": status["model"], "stream": True, "messages": [{"role": "system", "content": system}, *messages]}
    else:
        url = f"{status['base_url']}/responses"
        body = {"model": status["model"], "stream": True, "instructions": system,
                "input": [{"role": m["role"], "content": m["content"]} for m in messages]}
    async with httpx.AsyncClient(timeout=timeout, transport=transport or DEFAULT_TRANSPORT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:300]
                raise RuntimeError(f"Language model returned HTTP {response.status_code}: {detail}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if status["api"] == "chat_completions":
                    for choice in event.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            yield delta
                elif event.get("type") == "response.output_text.delta" and event.get("delta"):
                    yield event["delta"]
                elif event.get("type") in {"response.failed", "error"}:
                    raise RuntimeError(str(event.get("error") or event.get("response", {}).get("error") or "model error"))


def _says(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "say", **line} for line in lines]


def lesson_turn(ctx: BrainContext, text: str) -> list[dict[str, Any]] | None:
    """Teacher behaviour: reading pasted script, quizzing, re-reading, pacing. None = not a lesson turn."""
    lang = ctx.language
    en = lang == "english"
    if tutor.SLOWER.search(text) or tutor.FASTER.search(text):
        slower = bool(tutor.SLOWER.search(text))
        ctx.rate_scale = max(0.6, ctx.rate_scale - 0.15) if slower else min(1.3, ctx.rate_scale + 0.15)
        return _says([{"text": ("Of course, I'll speak more slowly." if slower else "Sure, a little faster.") if en
                       else ("Sawa, nitazungumza polepole zaidi." if slower else "Sawa, kwa kasi kidogo."), "segment": None}])
    if reading_mod.native_script_ratio(text) >= 0.25:
        reading = reading_mod.read_text(text, lang)
        if reading and reading["ok"]:
            ctx.lesson, ctx.quiz = reading, None
            return [{"type": "reading", "reading": reading}] + _says(reading_mod.narrate(reading, lang))
    if not ctx.lesson:
        return None
    if ctx.quiz:
        if tutor.STOP.search(text):
            lines = tutor.finish(ctx.quiz, lang)  # carries quiz_done so the card reveals its answers
            ctx.quiz = None
            return _says(lines)
        if tutor.REPEAT.search(text):
            return _says(tutor.repeat(ctx.lesson, ctx.quiz, lang))
        lines = tutor.answer(ctx.lesson, ctx.quiz, text, lang)
        if any(line.get("quiz_done") for line in lines):
            ctx.quiz = None
        return _says(lines)
    if tutor.STOP.search(text):
        return _says([{"text": "Okay. Show me something else whenever you like." if en else "Sawa. Nionyeshe kitu kingine wakati wowote.", "segment": None}])
    if tutor.START.search(text):
        ctx.quiz, lines = tutor.start(ctx.lesson, lang)
        return _says(lines)
    if tutor.READ_AGAIN.search(text):
        return [{"type": "reading", "reading": ctx.lesson}] + _says(reading_mod.narrate(ctx.lesson, lang))
    word = tutor.WORD_N.search(text)
    if word:
        index = int(word.group(1)) - 1
        segments = ctx.lesson["segments"]
        if 0 <= index < len(segments):
            single = {**ctx.lesson, "segments": [segments[index]], "summary": "", "translation": {}}
            lines = [line for line in reading_mod.narrate(single, lang, first_number=index + 1) if line["segment"] is not None]
            return _says([{**line, "segment": index} for line in lines])
        return _says([{"text": (f"This reading has {len(segments)} words." if en else f"Usomaji huu una maneno {len(segments)}."), "segment": None}])
    return None


async def think(ctx: BrainContext, user_text: str, transport: httpx.AsyncBaseTransport | None = None) -> AsyncIterator[dict[str, Any]]:
    """Yield {'type':'card'|'reading'|'say'|'delta'|'notice', ...} events for one user turn."""
    lesson = lesson_turn(ctx, user_text)
    if lesson is not None:
        for event in await localize_events(lesson, ctx, transport):
            yield event
        return
    tools = run_tools(user_text, ctx.persona)
    use_llm = llm_status()["configured"]
    if not use_llm:
        reply = offline_reply(user_text, ctx.persona, tools)
        for tool in tools:
            if tool.card:
                yield {"type": "card", "card": tool.card}
        for chunk in re.findall(r"\S+\s*", reply):
            yield {"type": "delta", "text": chunk}
        return
    system, messages = compile_prompt(ctx, user_text, [])
    produced = False
    try:
        async for event in run_agent(ctx, system, messages, transport):
            produced = produced or event["type"] in {"delta", "say"}
            yield event
    except Exception as exc:  # network, auth or model failure -> honest offline answer
        if produced:
            yield {"type": "notice", "text": f"The language model stopped early: {exc}"}
            return
        yield {"type": "notice", "text": f"Language model unavailable ({exc}); answering from the built-in tools."}
        for chunk in re.findall(r"\S+\s*", offline_reply(user_text, ctx.persona, tools)):
            yield {"type": "delta", "text": chunk}


# ------------------------------------------------------------------ seeing: photos and the live camera
GENERIC_QUESTION = re.compile(r"^\s*(?:what\s+does\s+(?:this|it|that|the)(?:\s+\w+){0,2}\s+say|what\s+(?:is\s+)?written(?:\s+here)?|read\s+(?:this|it)(?:\s+to\s+me)?|what\s+is\s+(?:this|that)|translate\s+(?:this|it)|inasema\s+nini|nisomee|hii\s+ni\s+nini|tafsiri\s+hii)?\s*[?.!]*\s*$", re.I)


def _vision_backends() -> tuple[bool, bool]:
    from ..vision import vision_status
    status = vision_status()
    requested = status["requested_backend"]
    local = bool(status["local"]["available"]) and requested in {"auto", "local", "hybrid"}
    model = bool(status["ai"]["configured"]) and requested in {"auto", "ai", "hybrid"}
    return local, model


async def see(ctx: BrainContext, image_data_url: str, question: str = "", source: str = "upload",
              transport: httpx.AsyncBaseTransport | None = None) -> AsyncIterator[dict[str, Any]]:
    """Read a photo or camera frame aloud, then teach it."""
    import asyncio

    from ..vision import _local_to_analysis, decode_image_data_url
    from ..vision_local import run_local_detection

    lang = ctx.language
    en = lang == "english"
    live = source == "live"
    metadata, raw = decode_image_data_url(image_data_url)
    local, model = _vision_backends()
    if not local and not model:
        if not live:
            yield {"type": "say", "segment": None, "text": (
                "I can't see images yet, because no vision model is connected to this app. You can paste the signs as text and I'll read them, "
                "or an administrator can set OPENAI_API_KEY or install the on-device sign detector." if en else
                "Bado siwezi kuona picha, kwa sababu hakuna modeli ya kuona iliyounganishwa. Bandika alama kama maandishi nami nitazisoma, "
                "au msimamizi aweke OPENAI_API_KEY au kitambuzi cha alama cha ndani.")}
        else:
            yield {"type": "live_unavailable"}
        return
    if not live:
        yield {"type": "say", "segment": None, "text": "Let me take a close look." if en else "Ngoja niangalie kwa makini."}

    detector_reading = None
    if local:
        detection = await asyncio.to_thread(run_local_detection, raw, metadata["mime"])
        detector_reading = reading_mod.reading_from_detector(_local_to_analysis(detection), lang)
    model_reading = None
    if model:
        try:
            model_reading = await reading_mod.read_image(image_data_url, lang, "" if GENERIC_QUESTION.match(question or "") else question)
        except Exception as exc:  # provider/network failure: fall back to the detector, honestly
            yield {"type": "notice", "text": f"Vision model unavailable: {exc}"}
    reading = model_reading or detector_reading
    if model_reading and detector_reading:
        mine = {s["transliteration"] for s in detector_reading["segments"]}
        theirs = {s["transliteration"] for s in model_reading["segments"]}
        if mine and not (mine & theirs):
            reading["notes"].append("The on-device detector and the vision model disagree on these signs; check them closely."
                                    if en else "Kitambuzi cha ndani na modeli ya kuona havikubaliani kuhusu alama hizi; zihakiki kwa makini.")
    if not reading or not reading.get("segments"):
        if live:
            yield {"type": "live_unchanged"}
            return
        empty = reading or {"script_name": "", "segments": [], "is_text_present": False, "translation": {}}
        empty["is_text_present"] = False
        for line in reading_mod.narrate({**empty, "script_name": empty.get("script_name", "")}, lang):
            yield {"type": "say", **line}
        return
    signature = "|".join(s["transliteration"] or s["original"] for s in reading["segments"])
    if live and signature == ctx.live_signature:
        yield {"type": "live_unchanged"}
        return
    ctx.live_signature = signature
    ctx.lesson, ctx.quiz = reading, None
    narration = [{"type": "reading", "reading": reading}]
    narration += [{"type": "say", **line} for line in reading_mod.narrate(reading, lang, detail="short" if live else "full")]
    if live:
        narration.append({"type": "say", "segment": None, "text": "Say read it to me and I'll teach it word by word." if en
                          else "Sema nisomee nami nitakufundisha neno kwa neno."})
    for event in await localize_events(narration, ctx, transport):
        yield event
    if question and not GENERIC_QUESTION.match(question) and llm_status()["configured"]:
        system, messages = compile_prompt(ctx, question, [])
        try:
            async for event in run_agent(ctx, system, messages, transport):
                yield event
        except Exception as exc:
            yield {"type": "notice", "text": f"The language model could not answer the follow-up: {exc}"}


# ------------------------------------------------------------------ agent loop: the model can use the whole platform
MAX_TOOL_ROUNDS = 4


def _model_request(status: dict[str, Any], system: str, items: list[dict[str, Any]], use_tools: bool) -> tuple[str, dict[str, Any]]:
    from .tools import chat_tools, responses_tools
    if status["api"] == "chat_completions":
        body: dict[str, Any] = {"model": status["model"], "stream": True, "messages": [{"role": "system", "content": system}, *items]}
        if use_tools:
            body["tools"] = chat_tools()
        return f"{status['base_url']}/chat/completions", body
    body = {"model": status["model"], "stream": True, "instructions": system, "input": items}
    if use_tools:
        body["tools"] = responses_tools()
    return f"{status['base_url']}/responses", body


async def _stream_round(url: str, body: dict[str, Any], api: str, transport: httpx.AsyncBaseTransport | None) -> AsyncIterator[tuple[str, Any]]:
    """Yield ('text', delta) and finally ('calls', [{'call_id','name','arguments'}])."""
    key = os.environ.get("ESHB_AVATAR_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    timeout = httpx.Timeout(float(os.environ.get("ESHB_AVATAR_LLM_TIMEOUT_SECONDS", "45")), connect=10.0)
    calls: dict[Any, dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=timeout, transport=transport or DEFAULT_TRANSPORT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:300]
                raise RuntimeError(f"Language model returned HTTP {response.status_code}: {detail}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if api == "chat_completions":
                    for choice in event.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield "text", delta["content"]
                        for call in delta.get("tool_calls") or []:
                            slot = calls.setdefault(call.get("index", 0), {"call_id": "", "name": "", "arguments": ""})
                            if call.get("id"):
                                slot["call_id"] = call["id"]
                            function = call.get("function") or {}
                            if function.get("name"):
                                slot["name"] = function["name"]
                            slot["arguments"] += function.get("arguments") or ""
                    continue
                kind = event.get("type")
                if kind == "response.output_text.delta" and event.get("delta"):
                    yield "text", event["delta"]
                elif kind == "response.output_item.done" and (event.get("item") or {}).get("type") == "function_call":
                    item = event["item"]
                    calls[item.get("id") or item.get("call_id")] = {"call_id": item.get("call_id"), "name": item.get("name"),
                                                                     "arguments": item.get("arguments") or "{}"}
                elif kind in {"response.failed", "error"}:
                    raise RuntimeError(str(event.get("error") or event.get("response", {}).get("error") or "model error"))
    yield "calls", [c for c in calls.values() if c.get("name")]


async def run_agent(ctx: "BrainContext", system: str, messages: list[dict[str, str]],
                    transport: httpx.AsyncBaseTransport | None = None, use_tools: bool = True) -> AsyncIterator[dict[str, Any]]:
    """Stream the model's reply; run any platform tools it calls and continue until it answers."""
    from .tools import execute
    status = llm_status()
    api = status["api"]
    items: list[dict[str, Any]] = [dict(m) for m in messages]
    for round_number in range(MAX_TOOL_ROUNDS + 1):
        url, body = _model_request(status, system, items, use_tools and round_number < MAX_TOOL_ROUNDS)
        calls: list[dict[str, Any]] = []
        async for kind, value in _stream_round(url, body, api, transport):
            if kind == "text":
                yield {"type": "delta", "text": value}
            else:
                calls = value
        if not calls:
            return
        if api == "chat_completions":
            items.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]})
        quiz_started = False
        for call in calls:
            yield {"type": "tool", "name": call["name"]}
            outcome = await execute(ctx, call["name"], call["arguments"])
            for event in outcome.events:
                yield event
            quiz_started = quiz_started or (call["name"] == "start_quiz" and outcome.output.get("ok"))
            output = json.dumps(outcome.output, ensure_ascii=False)[:8000]
            if api == "chat_completions":
                items.append({"role": "tool", "tool_call_id": call["call_id"], "content": output})
            else:
                items.append({"type": "function_call", "call_id": call["call_id"], "name": call["name"], "arguments": call["arguments"]})
                items.append({"type": "function_call_output", "call_id": call["call_id"], "output": output})
        if quiz_started:
            return  # the quiz question was already spoken; the learner answers next


# ------------------------------------------------------------------ explaining in any learner language
async def localize_events(events: list[dict[str, Any]], ctx: "BrainContext",
                          transport: httpx.AsyncBaseTransport | None = None) -> list[dict[str, Any]]:
    """Translate spoken lesson lines (written in English) into the learner's language, keeping word tags."""
    language = ctx.language
    says = [e for e in events if e["type"] == "say"]
    if language in FULL_OFFLINE_LANGUAGES or not says:
        return events
    texts = [e["text"] for e in says]
    translated: list[str] | None = None
    from ..universal_translation import TranslationError, UniversalTranslationRequest, _provider_status, universal_translate
    if any(p["configured"] for p in _provider_status().values()):
        try:
            result = await universal_translate(UniversalTranslationRequest(
                text=json.dumps([{"text": t} for t in texts], ensure_ascii=False), source_language="en",
                target_language=LANGUAGES[language]["mt"], format="json"))
            translated = [item["text"] for item in json.loads(result["translation"])]
        except (TranslationError, ValueError, KeyError, TypeError):
            translated = None
    if translated is None and llm_status()["configured"]:
        system = ("Translate each line into " + LANGUAGES[language]["label"] + " for a language learner. Keep ancient words, "
                  "transliterations and pronunciations exactly as written. Reply with ONLY a JSON array of strings, same length and order.")
        try:
            chunks = [value async for kind, value in _stream_round(*_model_request(llm_status(), system,
                      [{"role": "user", "content": json.dumps(texts, ensure_ascii=False)}], False), llm_status()["api"], transport)
                      if kind == "text"]
            candidate = json.loads(re.sub(r"^```(?:json)?|```$", "", "".join(chunks).strip()).strip())
            if isinstance(candidate, list) and len(candidate) == len(texts):
                translated = [str(x) for x in candidate]
        except Exception:
            translated = None
    if translated is None or len(translated) != len(texts):
        if not ctx.language_notice_given:
            ctx.language_notice_given = True
            label = LANGUAGES[language]["label"]
            return [{"type": "notice", "text": f"Explaining in English: lessons in {label} need a language model or translation provider."}] + events
        return events
    out, index = [], 0
    for event in events:
        if event["type"] == "say":
            out.append({**event, "text": translated[index]})
            index += 1
        else:
            out.append(event)
    return out
