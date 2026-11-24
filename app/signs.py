"""Complete Egyptian hieroglyph sign catalog from the Unicode Unikemet database.

Every encoded sign (basic block and Extended-A) with its Unikemet catalog number, the
Gardiner/JSesh, Hieroglyphica and IFAO codes, a description, its functions (logogram,
phonemogram, classifier, phono-repeater) and functional values, orientation constraints
(no mirror / no rotate) and alternative encodings. Variants are signs sharing a Gardiner
base code (A1, A1A, A1B…) or an Unikemet alternative sequence.

Source: Unikemet.txt, Unicode Character Database, Unicode License v3.
"""
from __future__ import annotations

import gzip
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent / "data" / "signs" / "unikemet.json.gz"
FUNCTION_ROLES = {"logogram": "logogram", "phonemogram": "phonogram", "classifier": "classifier",
                  "phono-repeater": "phonetic_complement", "interpretant": "interpretant"}
# Unikemet writes Egyptological yod as ꞽ and q as ḳ; the app's transliteration uses j and q.
TRANSLIT_NORMAL = {"ꞽ": "j", "ḳ": "q", "Ꞽ": "J", "Ḳ": "Q"}


def normalize_value(value: str) -> str:
    return "".join(TRANSLIT_NORMAL.get(c, c) for c in unicodedata.normalize("NFC", value))


def _gardiner_base(code: str) -> str:
    """A1 -> A1, A1A -> A1, Aa28 -> Aa28, N35A -> N35."""
    m = re.match(r"^([A-Z][a-z]?\d+)", code or "")
    return m.group(1) if m else (code or "")


def _functions(text: str) -> list[dict[str, str]]:
    """'Logogram (to build)' / 'Phonemogram/classifier messenger' -> [{role, detail}]."""
    out = []
    if not text:
        return out
    m = re.match(r"^([A-Za-z/\-?]+)\s*(.*)$", text.strip())
    roles = m.group(1).split("/") if m else [text]
    detail = (m.group(2) if m else "").strip().strip("()")
    for role in roles:
        key = role.strip().lower()
        out.append({"role": FUNCTION_ROLES.get(key, "uncertain" if key == "?" else key), "detail": detail})
    return out


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    with gzip.open(DATA, "rt", encoding="utf-8") as handle:
        raw = json.load(handle)
    by_glyph: dict[str, dict[str, Any]] = {}
    by_code: dict[str, str] = {}
    by_value: dict[str, list[str]] = {}
    by_base: dict[str, list[str]] = {}
    for item in raw["signs"]:
        cp = int(item["cp"][2:], 16)
        glyph = chr(cp)
        values = item.get("values", [])
        record = {
            "glyph": glyph,
            "codepoint": item["cp"],
            "unicode_name": unicodedata.name(glyph, f"EGYPTIAN HIEROGLYPH {item.get('unik', '')}".strip()),
            "catalog": item.get("catalog"),
            "gardiner": item.get("jsesh") or None,
            "unikemet_code": item.get("unik"),
            "hieroglyphica": item.get("hieroglyphica"),
            "ifao": item.get("ifao"),
            "core": {"C": "core", "L": "legacy"}.get(item.get("core", ""), "non-core"),
            "description": item.get("description", ""),
            "functions": _functions(item.get("function", "")),
            "values": [normalize_value(v) for v in values],
            "values_unikemet": values,
            "orientation": {"can_mirror": not item.get("no_mirror", False), "can_rotate": not item.get("no_rotate", False)},
            "alternative_sequence": item.get("alt_sequence", []),
            "block": "Egyptian Hieroglyphs" if cp <= 0x1342F else "Egyptian Hieroglyphs Extended-A",
        }
        by_glyph[glyph] = record
        for code in (item.get("jsesh"), item.get("unik"), item.get("hieroglyphica"), item.get("catalog")):
            if code:
                by_code.setdefault(code.upper(), glyph)
        for value in record["values"]:
            by_value.setdefault(value.lower(), []).append(glyph)
        if record["gardiner"]:
            by_base.setdefault(_gardiner_base(record["gardiner"]).upper(), []).append(glyph)
    return {"meta": {k: raw[k] for k in ("source", "date", "license", "count")}, "glyph": by_glyph, "code": by_code,
            "value": by_value, "base": by_base}


def catalog_info() -> dict[str, Any]:
    data = _load()
    signs = data["glyph"].values()
    return {**data["meta"], "with_values": sum(1 for s in signs if s["values"]),
            "with_gardiner_code": sum(1 for s in signs if s["gardiner"]),
            "core_signs": sum(1 for s in signs if s["core"] == "core"),
            "extended_a": sum(1 for s in signs if s["block"].endswith("Extended-A"))}


def sign(glyph_or_code: str) -> dict[str, Any] | None:
    """Look up by glyph, Gardiner/JSesh code (A1, Aa28), Unikemet code (A001) or catalog number (A-01-001)."""
    data = _load()
    key = (glyph_or_code or "").strip()
    if key in data["glyph"]:
        return data["glyph"][key]
    glyph = data["code"].get(key.upper())
    return data["glyph"].get(glyph) if glyph else None


def variants(glyph_or_code: str) -> list[dict[str, Any]]:
    """Other encoded forms of the same sign: shared Gardiner base code or Unikemet alternative sequence."""
    record = sign(glyph_or_code)
    if not record:
        return []
    data = _load()
    out = []
    for glyph in data["base"].get(_gardiner_base(record["gardiner"] or "").upper(), []):
        if glyph != record["glyph"]:
            out.append({**_brief(data["glyph"][glyph]), "relation": "same Gardiner base"})
    for other in data["glyph"].values():
        if record["codepoint"] in other["alternative_sequence"]:
            out.append({**_brief(other), "relation": "encoded alternative (mirrored/sequence)"})
    return out


def _brief(record: dict[str, Any]) -> dict[str, Any]:
    return {k: record[k] for k in ("glyph", "codepoint", "gardiner", "description", "values")}


def by_value(value: str, limit: int = 30) -> list[dict[str, Any]]:
    data = _load()
    glyphs = data["value"].get(normalize_value(value).lower(), [])
    return [_brief(data["glyph"][g]) | {"functions": data["glyph"][g]["functions"]} for g in glyphs[:limit]]


def search(query: str, limit: int = 30) -> list[dict[str, Any]]:
    """Search descriptions, functions, codes and values."""
    q = normalize_value(query).lower().strip()
    if not q:
        return []
    exact = sign(query)
    results = [exact] if exact else []
    for record in _load()["glyph"].values():
        if record in results:
            continue
        hay = " ".join([record["description"], record["gardiner"] or "", " ".join(record["values"]),
                        " ".join(f["detail"] for f in record["functions"])]).lower()
        if q in hay:
            results.append(record)
        if len(results) >= limit:
            break
    return [_brief(r) | {"functions": r["functions"]} for r in results]
