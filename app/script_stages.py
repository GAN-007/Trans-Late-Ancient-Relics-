"""The scripts of Egyptian across its history and how the platform handles each.

Egyptian was written in four scripts over 4,000 years. Only hieroglyphs and Coptic are in
Unicode; hieratic and Demotic are cursive scripts that Egyptologists publish as a hieroglyphic
transcription (hieratic) or a transliteration (Demotic). The platform follows that practice.
"""
from __future__ import annotations

from typing import Any

STAGES: list[dict[str, Any]] = [
    {"id": "hieroglyphic", "name": "Hieroglyphic", "dates": "c. 3250 BCE - 394 CE", "languages": ["archaic", "old", "middle", "late egyptian"],
     "unicode": "Egyptian Hieroglyphs (U+13000-1345F) and Extended-A (U+13460-143FF); quadrat layout by format controls",
     "direction": "right to left (usually), left to right or in columns; signs face the start of the line",
     "platform": ["sign catalog (Unikemet)", "quadrat parser and renderer", "word reader and lessons", "camera and photo reading",
                  "attestation database (TLA)"]},
    {"id": "cursive_hieroglyphic", "name": "Cursive hieroglyphs", "dates": "c. 2000 BCE - 1st millennium BCE",
     "languages": ["middle egyptian (religious texts)"], "unicode": "transcribed with standard hieroglyphs",
     "direction": "usually columns, right to left", "platform": ["read through the hieroglyphic pipeline after transcription"]},
    {"id": "hieratic", "name": "Hieratic", "dates": "c. 3200 BCE - 3rd c. CE (Old, Middle, New and abnormal hieratic)",
     "languages": ["old", "middle", "late egyptian"], "unicode": "not encoded; published as a hieroglyphic transcription (Möller, Hieratische Paläographie)",
     "direction": "right to left (lines; earlier also columns)",
     "platform": ["the vision model transcribes hieratic into hieroglyphs and the deterministic readers cross-check it",
                  "TLA records keep the script of each text (e.g. Neuhieratisch)"]},
    {"id": "demotic", "name": "Demotic", "dates": "c. 650 BCE - 452 CE", "languages": ["demotic"],
     "unicode": "not encoded; published as transliteration (Chicago Demotic Dictionary conventions)",
     "direction": "right to left",
     "platform": ["the vision model gives a transliteration", "Demotic lemmas (TLA d-numbers) and their Coptic descendants are linked "
                  "in the attestation database where the Coptic lexicon records them"]},
    {"id": "coptic", "name": "Coptic", "dates": "c. 3rd - 11th c. CE (literary use later)", "languages": ["coptic (Sahidic, Bohairic, "
     "Akhmimic, Lycopolitan, Mesokemic, Fayyumic …)"], "unicode": "Coptic (U+2C80-2CFF) and Greek and Coptic (U+03E2-03EF)",
     "direction": "left to right",
     "platform": ["word-by-word reader with 11,283 dictionary entries (Comprehensive Coptic Lexicon)", "dialect forms",
                  "Sahidic pronunciation", "Egyptian-to-Coptic etymology bridge for vocalization"]},
]


def stages() -> list[dict[str, Any]]:
    return STAGES
