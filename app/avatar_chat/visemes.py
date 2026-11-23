"""Text -> facial motion timeline, using ARKit blendshape channel names.

OpenAvatarChat's LAM driver turns speech audio into the 52 ARKit blendshapes
(jawOpen, mouthFunnel, ...) and the browser renders them. Running that model
needs a GPU, so this module produces the same kind of motion data from the
reply text instead: each letter group maps to a viseme, each viseme to a small
set of ARKit channels, timed to the speaking rate the browser voice uses.

The browser re-times the track against real speech boundary events when the
voice exposes them, so lips stay in step with the audio.
"""
from __future__ import annotations

import unicodedata
from typing import Any

CHANNELS = [
    "jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "mouthSmileLeft",
    "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight", "mouthPressLeft",
    "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight", "tongueOut",
]

# viseme -> ARKit channel weights (0..1)
VISEMES: dict[str, dict[str, float]] = {
    "sil": {"mouthClose": 0.1},
    "AA": {"jawOpen": 0.7, "mouthLowerDownLeft": 0.3, "mouthLowerDownRight": 0.3},
    "E": {"jawOpen": 0.4, "mouthStretchLeft": 0.45, "mouthStretchRight": 0.45},
    "I": {"jawOpen": 0.25, "mouthSmileLeft": 0.5, "mouthSmileRight": 0.5},
    "O": {"jawOpen": 0.5, "mouthFunnel": 0.65},
    "U": {"jawOpen": 0.2, "mouthPucker": 0.75},
    "PP": {"mouthClose": 0.9, "mouthPressLeft": 0.6, "mouthPressRight": 0.6},
    "FF": {"jawOpen": 0.12, "mouthLowerDownLeft": 0.1, "mouthLowerDownRight": 0.1, "mouthPressLeft": 0.3, "mouthPressRight": 0.3},
    "TH": {"jawOpen": 0.2, "tongueOut": 0.35},
    "DD": {"jawOpen": 0.28},
    "KK": {"jawOpen": 0.35},
    "CH": {"jawOpen": 0.25, "mouthFunnel": 0.35, "mouthPucker": 0.2},
    "SS": {"jawOpen": 0.12, "mouthStretchLeft": 0.3, "mouthStretchRight": 0.3},
    "NN": {"jawOpen": 0.18},
    "RR": {"jawOpen": 0.25, "mouthPucker": 0.3},
}

_DIGRAPHS = {"th": "TH", "sh": "CH", "ch": "CH", "ng": "NN", "ny": "NN", "ph": "FF", "wh": "U", "oo": "U", "ee": "I", "ai": "E", "ou": "O"}
_LETTERS = {
    "a": "AA", "e": "E", "i": "I", "o": "O", "u": "U", "y": "I", "w": "U",
    "b": "PP", "p": "PP", "m": "PP", "f": "FF", "v": "FF",
    "t": "DD", "d": "DD", "n": "NN", "l": "DD", "k": "KK", "g": "KK", "c": "KK", "q": "KK", "x": "KK", "h": "KK",
    "s": "SS", "z": "SS", "j": "CH", "r": "RR",
}
VOWELS = {"AA", "E", "I", "O", "U"}


def _base_letters(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def visemes_for(text: str) -> list[str]:
    """Approximate viseme sequence for a sentence (works for English, Swahili and transliteration)."""
    letters = _base_letters(text)
    out: list[str] = []
    i = 0
    while i < len(letters):
        pair = letters[i:i + 2]
        if pair in _DIGRAPHS:
            out.append(_DIGRAPHS[pair])
            i += 2
            continue
        char = letters[i]
        if char in _LETTERS:
            out.append(_LETTERS[char])
        elif char.isspace() or unicodedata.category(char)[0] == "P":
            if out and out[-1] != "sil":
                out.append("sil")
        elif char.isalpha():
            out.append("AA" if ord(char) % 2 else "E")  # other scripts: open/close rhythm
        i += 1
    while out and out[-1] == "sil":
        out.pop()
    return out


def motion_track(text: str, rate: float = 0.95, fps: int = 30) -> dict[str, Any]:
    """Keyframes of ARKit channel weights for one spoken sentence.

    rate is the browser speech-synthesis rate (1.0 = normal); English averages
    roughly 13 phonemes per second at rate 1.0.
    """
    sequence = visemes_for(text)
    per_viseme = 1.0 / (13.0 * max(rate, 0.3))
    frames: list[dict[str, Any]] = []
    t = 0.0
    for viseme in sequence:
        weight = per_viseme * (1.35 if viseme in VOWELS else 0.8 if viseme != "sil" else 1.6)
        frames.append({"t": round(t, 3), "v": viseme, "w": VISEMES[viseme]})
        t += weight
    frames.append({"t": round(t, 3), "v": "sil", "w": VISEMES["sil"]})
    return {"channels": CHANNELS, "fps": fps, "duration": round(t, 3), "frames": frames}
