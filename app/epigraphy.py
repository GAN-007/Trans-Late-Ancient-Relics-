from __future__ import annotations

import unicodedata
from dataclasses import dataclass, asdict
from typing import Any

from .egyptian import UNILITERALS

# Unicode 17.0 ranges. Extended-A was added for the substantially larger
# Greco-Roman/sign inventory. Format controls encode quadrat layout rather than
# phonetic value and must never be mistaken for signs.
BASIC_START, BASIC_END = 0x13000, 0x1342F
FORMAT_START, FORMAT_END = 0x13430, 0x1345F
EXT_A_START, EXT_A_END = 0x13460, 0x143FF

FORMAT_CONTROLS: dict[int, dict[str, str]] = {
    0x13430: {"name": "vertical_joiner", "mdc": ":", "meaning": "vertical/subordinate join"},
    0x13431: {"name": "horizontal_joiner", "mdc": "*", "meaning": "horizontal/juxtaposed join"},
    0x13432: {"name": "insert_top_start", "mdc": "", "meaning": "insert at top start"},
    0x13433: {"name": "insert_bottom_start", "mdc": "", "meaning": "insert at bottom start"},
    0x13434: {"name": "insert_top_end", "mdc": "", "meaning": "insert at top end"},
    0x13435: {"name": "insert_bottom_end", "mdc": "", "meaning": "insert at bottom end"},
    0x13436: {"name": "overlay_middle", "mdc": "", "meaning": "overlay signs"},
    0x13437: {"name": "begin_segment", "mdc": "(", "meaning": "begin grouped segment"},
    0x13438: {"name": "end_segment", "mdc": ")", "meaning": "end grouped segment"},
    0x13439: {"name": "insert_middle", "mdc": "", "meaning": "insert at middle"},
    0x1343A: {"name": "insert_top", "mdc": "", "meaning": "insert at top"},
    0x1343B: {"name": "insert_bottom", "mdc": "", "meaning": "insert at bottom"},
    0x1343C: {"name": "begin_enclosure", "mdc": "", "meaning": "begin enclosure"},
    0x1343D: {"name": "end_enclosure", "mdc": "", "meaning": "end enclosure"},
    0x1343E: {"name": "begin_walled_enclosure", "mdc": "", "meaning": "begin walled enclosure"},
    0x1343F: {"name": "end_walled_enclosure", "mdc": "", "meaning": "end walled enclosure"},
    0x13440: {"name": "mirror_horizontally", "mdc": "", "meaning": "mirror previous/associated sign"},
    0x13441: {"name": "full_blank", "mdc": "", "meaning": "full blank"},
    0x13442: {"name": "half_blank", "mdc": "", "meaning": "half blank"},
    0x13443: {"name": "lost_sign", "mdc": "", "meaning": "lost sign"},
    0x13444: {"name": "half_lost_sign", "mdc": "", "meaning": "half lost sign"},
    0x13445: {"name": "tall_lost_sign", "mdc": "", "meaning": "tall lost sign"},
    0x13446: {"name": "wide_lost_sign", "mdc": "", "meaning": "wide lost sign"},
    0x13447: {"name": "damaged_top_start", "mdc": "", "meaning": "damage modifier"},
    0x13448: {"name": "damaged_bottom_start", "mdc": "", "meaning": "damage modifier"},
    0x13449: {"name": "damaged_start", "mdc": "", "meaning": "damage modifier"},
    0x1344A: {"name": "damaged_top_end", "mdc": "", "meaning": "damage modifier"},
    0x1344B: {"name": "damaged_top", "mdc": "", "meaning": "damage modifier"},
    0x1344C: {"name": "damaged_bottom_start_top_end", "mdc": "", "meaning": "damage modifier"},
    0x1344D: {"name": "damaged_start_top", "mdc": "", "meaning": "damage modifier"},
    0x1344E: {"name": "damaged_bottom_end", "mdc": "", "meaning": "damage modifier"},
    0x1344F: {"name": "damaged_top_start_bottom_end", "mdc": "", "meaning": "damage modifier"},
    0x13450: {"name": "damaged_bottom", "mdc": "", "meaning": "damage modifier"},
    0x13451: {"name": "damaged_start_bottom", "mdc": "", "meaning": "damage modifier"},
    0x13452: {"name": "damaged_end", "mdc": "", "meaning": "damage modifier"},
    0x13453: {"name": "damaged_top_end", "mdc": "", "meaning": "damage modifier"},
    0x13454: {"name": "damaged_bottom_end", "mdc": "", "meaning": "damage modifier"},
    0x13455: {"name": "damaged", "mdc": "", "meaning": "damage modifier"},
}


@dataclass(frozen=True)
class SignInfo:
    glyph: str
    gardiner: str | None
    values: tuple[str, ...]
    possible_functions: tuple[str, ...]
    semantic_class: str | None = None
    note: str = ""


# This is deliberately a small, reviewed teaching core rather than pretending to
# be a complete Gardiner/Unikemet database. Unknown Unicode signs remain unknown.
CORE_SIGNS: dict[str, SignInfo] = {
    "𓄤": SignInfo("𓄤", "F35", ("nfr",), ("triliteral", "logogram"), "quality", "Common nfr sign."),
    "𓋹": SignInfo("𓋹", "S34", ("ꜥnḫ",), ("triliteral", "logogram"), "life", "Ankh sign."),
    "𓊵": SignInfo("𓊵", "R4", ("ḥtp",), ("triliteral", "logogram"), "offering", "Offering table sign."),
    "𓉐": SignInfo("𓉐", "O1", ("pr",), ("biliteral", "logogram", "determinative"), "building", "House plan; function depends on context."),
    "𓄣": SignInfo("𓄣", "F34", ("jb",), ("biliteral", "logogram"), "body", "Heart sign."),
    "𓂓": SignInfo("𓂓", "D28", ("kꜣ",), ("biliteral", "logogram"), "religion", "Ka sign."),
    "𓅡": SignInfo("𓅡", "G29", ("bꜣ",), ("biliteral", "logogram"), "religion", "Ba-bird sign."),
    "𓇳": SignInfo("𓇳", "N5", ("rꜥ",), ("biliteral", "logogram", "determinative"), "sun/day", "Sun disk; may classify solar/day vocabulary."),
    "𓊹": SignInfo("𓊹", "R8", ("nṯr",), ("triliteral", "logogram", "determinative"), "divinity", "Divine standard."),
    "𓊽": SignInfo("𓊽", "R11", ("ḏd",), ("biliteral", "logogram"), "stability", "Djed pillar."),
    "𓌀": SignInfo("𓌀", "S40", ("wꜣs",), ("triliteral", "logogram"), "power", "Was-sceptre."),
    "𓇾": SignInfo("𓇾", "N16", ("tꜣ",), ("biliteral", "logogram", "determinative"), "land", "Land sign."),
    "𓇯": SignInfo("𓇯", "N1", ("pt",), ("biliteral", "logogram", "determinative"), "sky", "Sky sign."),
    "𓈗": SignInfo("𓈗", "N35A", ("mw",), ("biliteral", "logogram", "determinative"), "water", "Water group."),
    "𓀀": SignInfo("𓀀", "A1", (), ("determinative", "logogram"), "male person", "Common person/man classifier; context determines function."),
    "𓁐": SignInfo("𓁐", "B1", (), ("determinative", "logogram"), "female person", "Common woman/female classifier; context determines function."),
    "𓊖": SignInfo("𓊖", "O49", (), ("determinative", "logogram"), "settlement", "Town/settlement classifier."),
    "𓈉": SignInfo("𓈉", "N25", (), ("determinative", "logogram"), "foreign/hill land", "Foreign/hill-country classifier."),
    "𓏤": SignInfo("𓏤", "Z1", (), ("ideogram_stroke", "determinative"), "ideogram marker", "Stroke can mark ideographic/logographic use; it is not spoken."),
}

for value, row in UNILITERALS.items():
    glyph = row["glyph"]
    existing = CORE_SIGNS.get(glyph)
    if existing is None:
        CORE_SIGNS[glyph] = SignInfo(
            glyph=glyph,
            gardiner=row.get("gardiner"),
            values=(value,),
            possible_functions=("uniliteral", "phonogram", "phonetic_complement"),
            note=f"Core one-consonant sign: {row.get('name', '')}.",
        )


def is_format_control(char: str) -> bool:
    return len(char) == 1 and FORMAT_START <= ord(char) <= FORMAT_END


def is_hieroglyph(char: str) -> bool:
    if len(char) != 1:
        return False
    cp = ord(char)
    return BASIC_START <= cp <= BASIC_END or EXT_A_START <= cp <= EXT_A_END


def unicode_block(char: str) -> str | None:
    if not char:
        return None
    cp = ord(char)
    if BASIC_START <= cp <= BASIC_END:
        return "Egyptian Hieroglyphs"
    if FORMAT_START <= cp <= FORMAT_END:
        return "Egyptian Hieroglyph Format Controls"
    if EXT_A_START <= cp <= EXT_A_END:
        return "Egyptian Hieroglyphs Extended-A"
    return None


def tokenize_hieroglyphic_text(text: str) -> dict[str, Any]:
    signs: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    for index, char in enumerate(text):
        cp = ord(char)
        if is_hieroglyph(char):
            info = CORE_SIGNS.get(char)
            signs.append(
                {
                    "index": index,
                    "glyph": char,
                    "codepoint": f"U+{cp:05X}",
                    "unicode_name": unicodedata.name(char, "UNNAMED EGYPTIAN SIGN"),
                    "unicode_block": unicode_block(char),
                    "known": info is not None,
                    "sign": asdict(info) if info else None,
                }
            )
        elif is_format_control(char):
            item = FORMAT_CONTROLS.get(cp, {"name": "reserved_or_future_control", "mdc": "", "meaning": "format control"})
            controls.append({"index": index, "char": char, "codepoint": f"U+{cp:05X}", **item})
        elif not char.isspace():
            ignored.append({"index": index, "char": char, "codepoint": f"U+{cp:04X}"})
    return {"signs": signs, "format_controls": controls, "non_hieroglyphic": ignored}


def _phonetic_complement_candidates(signs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for i, item in enumerate(signs):
        info = item.get("sign") or {}
        functions = set(info.get("possible_functions") or [])
        values = list(info.get("values") or [])
        if not values or not ({"biliteral", "triliteral"} & functions):
            continue
        value = values[0]
        following = signs[i + 1 : i + 3]
        following_values: list[str] = []
        for candidate in following:
            cinfo = candidate.get("sign") or {}
            funcs = set(cinfo.get("possible_functions") or [])
            vals = cinfo.get("values") or []
            if "uniliteral" in funcs and vals:
                following_values.append(vals[0])
            else:
                break
        if not following_values:
            continue
        suffix = "".join(following_values)
        if value.endswith(suffix) or any(value.endswith(v) for v in following_values):
            results.append(
                {
                    "host_index": item["index"],
                    "host_glyph": item["glyph"],
                    "host_value": value,
                    "complement_indices": [x["index"] for x in following[: len(following_values)]],
                    "complement_values": following_values,
                    "certainty": "candidate",
                    "note": "The following uniliteral(s) repeat consonantal information already present in a multi-consonant sign and may be phonetic complements. Context and spelling tradition must confirm this.",
                }
            )
    return results


def analyze_hieroglyphic_text(text: str) -> dict[str, Any]:
    tokenized = tokenize_hieroglyphic_text(text)
    signs = tokenized["signs"]
    determinatives: list[dict[str, Any]] = []
    phonograms: list[dict[str, Any]] = []
    logograms: list[dict[str, Any]] = []
    for position, item in enumerate(signs):
        info = item.get("sign") or {}
        functions = set(info.get("possible_functions") or [])
        descriptor = {
            "index": item["index"],
            "glyph": item["glyph"],
            "gardiner": info.get("gardiner"),
            "values": info.get("values") or [],
            "semantic_class": info.get("semantic_class"),
            "possible_functions": sorted(functions),
        }
        if functions & {"uniliteral", "phonogram", "biliteral", "triliteral"}:
            phonograms.append(descriptor)
        if "logogram" in functions:
            logograms.append({**descriptor, "certainty": "possible"})
        if "determinative" in functions:
            # Final position raises the prior probability but never proves the role.
            determinatives.append(
                {
                    **descriptor,
                    "certainty": "candidate",
                    "position_evidence": "word/sequence-final" if position == len(signs) - 1 else "non-final",
                }
            )

    controls = tokenized["format_controls"]
    layout = {
        "has_layout_controls": bool(controls),
        "vertical_joins": sum(1 for c in controls if c["name"] == "vertical_joiner"),
        "horizontal_joins": sum(1 for c in controls if c["name"] == "horizontal_joiner"),
        "damage_markers": sum(1 for c in controls if "damaged" in c["name"] or "lost" in c["name"]),
        "enclosures": sum(1 for c in controls if "enclosure" in c["name"]),
    }
    unknown_signs = [s for s in signs if not s["known"]]
    return {
        "source": text,
        "sign_count": len(signs),
        "signs": signs,
        "phonogram_candidates": phonograms,
        "logogram_candidates": logograms,
        "determinative_candidates": determinatives,
        "phonetic_complement_candidates": _phonetic_complement_candidates(signs),
        "layout": layout,
        "format_controls": controls,
        "unknown_signs": unknown_signs,
        "non_hieroglyphic": tokenized["non_hieroglyphic"],
        "reading_direction": {
            "value": "undetermined_from_unicode_alone",
            "note": "Egyptian text may run right-to-left or left-to-right. Plain Unicode code-point order does not reliably encode the original facing direction; use image evidence/sign orientation or an explicit user override.",
        },
        "coverage": {
            "known_core_signs": len(signs) - len(unknown_signs),
            "unknown_or_unmapped_signs": len(unknown_signs),
            "warning": "The built-in catalog is a reviewed teaching core, not a complete Unikemet/Gardiner database.",
        },
    }


def gardiner_core_lookup(code: str) -> dict[str, Any] | None:
    code = code.strip().upper()
    for info in CORE_SIGNS.values():
        if (info.gardiner or "").upper() == code:
            return asdict(info)
    return None


def epigraphy_capabilities() -> dict[str, Any]:
    return {
        "unicode_basic": f"U+{BASIC_START:05X}–U+{BASIC_END:05X}",
        "unicode_format_controls": f"U+{FORMAT_START:05X}–U+{FORMAT_END:05X}",
        "unicode_extended_a": f"U+{EXT_A_START:05X}–U+{EXT_A_END:05X}",
        "known_core_signs": len(CORE_SIGNS),
        "format_controls_documented": len(FORMAT_CONTROLS),
        "supports": [
            "Unicode sign detection",
            "format-control separation",
            "core sign-function candidates",
            "candidate determinatives",
            "candidate phonetic complements",
            "damage/lost-sign controls",
        ],
        "does_not_claim": [
            "complete sign-function disambiguation",
            "automatic reading direction from code-point order",
            "complete Gardiner/Unikemet coverage",
        ],
    }
