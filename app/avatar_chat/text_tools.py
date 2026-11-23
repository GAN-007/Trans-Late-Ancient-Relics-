"""Streaming text helpers for the avatar's voice.

Ported and adapted from OpenAvatarChat (Apache-2.0):
  src/handlers/tts/token_buffer.py   -> TokenBuffer / SentenceBuffer
  src/engine_utils/text_filter.py    -> speakable()

Changes from the original: Ethiopic, Old Italic, cuneiform, hieroglyph and other
historic scripts are treated as word characters (the original only knew modern
scripts), Ethiopic sentence marks are recognized, and the filter keeps every
script instead of stripping non-Latin/non-CJK characters.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Scripts written without spaces can be spoken character by character.
_IMMEDIATE_RANGES = (
    (0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3040, 0x30FF), (0xAC00, 0xD7AF), (0x0E00, 0x0E7F),
)
SENTENCE_END = set(".!?;。！？；؟।።")
CLAUSE_END = set(",:，：、፣፥")


def _immediate(char: str) -> bool:
    if char.isspace():
        return True
    code = ord(char)
    if any(lo <= code <= hi for lo, hi in _IMMEDIATE_RANGES):
        return True
    return unicodedata.category(char)[0] in {"P", "S"} and char not in "*_#`"


@dataclass
class TokenBuffer:
    """Hold back partial words from a token stream so speech never cuts a word in half."""

    buffer: str = ""
    max_buffer_chars: int = 200

    def process(self, token: str | None) -> str:
        if not token:
            return ""
        out: list[str] = []
        for char in token:
            if _immediate(char):
                if self.buffer:
                    out.append(self.buffer)
                    self.buffer = ""
                out.append(char)
            else:
                self.buffer += char
                if len(self.buffer) >= self.max_buffer_chars:
                    out.append(self.buffer)
                    self.buffer = ""
        return "".join(out)

    def flush(self) -> str:
        rest, self.buffer = self.buffer, ""
        return rest


@dataclass
class SentenceBuffer(TokenBuffer):
    """Emit whole sentences (optionally clauses) from a token stream."""

    split_on_clause: bool = False
    min_chars: int = 2
    _pending: str = field(default="", init=False)

    def process(self, token: str | None) -> list[str]:  # type: ignore[override]
        self._pending += super().process(token)
        sentences: list[str] = []
        start = 0
        for index, char in enumerate(self._pending):
            if char in SENTENCE_END or (self.split_on_clause and char in CLAUSE_END):
                piece = self._pending[start:index + 1]
                if len(piece.strip()) >= self.min_chars:
                    sentences.append(piece.strip())
                    start = index + 1
        self._pending = self._pending[start:]
        return sentences

    def flush(self) -> list[str]:  # type: ignore[override]
        rest = (self._pending + super().flush()).strip()
        self._pending = ""
        return [rest] if rest else []


_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_HEADING = re.compile(r"^#{1,6}\s+", re.M)
_LIST = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+", re.M)
_QUOTE = re.compile(r"^>\s+", re.M)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(.+?)\1")
_SPECIAL = re.compile(r"<\|.*?\|>")


def speakable(text: str) -> str:
    """Strip markdown and code so text-to-speech reads only words. All scripts are kept."""
    if not text:
        return ""
    text = _CODE_BLOCK.sub(" ", text)
    text = _INLINE_CODE.sub(lambda m: m.group(0).strip("`"), text)
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    text = _SPECIAL.sub("", text)
    text = _HEADING.sub("", text)
    text = _LIST.sub("", text)
    text = _QUOTE.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = text.replace("|", " ").replace("*", "")
    text = re.sub(r"[\n\r\t]+", " ", text)
    return re.sub(r" {2,}", " ", text).strip()
