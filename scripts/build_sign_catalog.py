"""Build app/data/signs/unikemet.json.gz from the Unicode Unikemet data file.

Unikemet.txt is the Unicode Character Database's normative property file for Egyptian
hieroglyphs (Unicode License v3). Download it from
https://www.unicode.org/Public/UCD/latest/ucd/Unikemet.txt (or the unicode-org/unicodetools
repository) and run:

    python scripts/build_sign_catalog.py path/to/Unikemet.txt
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "signs" / "unikemet.json.gz"
FIELDS = {"kEH_Cat": "catalog", "kEH_Core": "core", "kEH_Desc": "description", "kEH_Func": "function",
          "kEH_FVal": "values", "kEH_UniK": "unik", "kEH_JSesh": "jsesh", "kEH_HG": "hieroglyphica",
          "kEH_IFAO": "ifao", "kEH_AltSeq": "alt_sequence", "kEH_NoMirror": "no_mirror", "kEH_NoRotate": "no_rotate"}


def build(source: Path) -> dict:
    header = []
    signs: dict[str, dict] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            if len(header) < 3:
                header.append(line.lstrip("# ").strip())
            continue
        parts = line.split("\t")
        if len(parts) != 3 or parts[1] not in FIELDS:
            continue
        cp, tag, value = parts
        entry = signs.setdefault(cp, {"cp": cp})
        key = FIELDS[tag]
        if key == "values":
            entry[key] = [v.strip() for v in re.split(r"\s*[;,]\s*", value) if v.strip()]
        elif key in {"no_mirror", "no_rotate"}:
            entry[key] = value.strip().upper() == "Y"
        elif key == "alt_sequence":
            entry[key] = [f"U+{c}" for c in value.split()]
        else:
            entry[key] = value.strip()
    return {"source": header[0] if header else "Unikemet", "date": header[1].replace("Date:", "").strip() if len(header) > 1 else "",
            "license": "Unicode License v3 (https://www.unicode.org/license.txt)", "count": len(signs),
            "signs": list(signs.values())}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"{data['count']} signs from {data['source']} -> {OUT}")


if __name__ == "__main__":
    main()


def build_metrics(font_path: Path) -> Path:
    """Glyph bounding boxes from the bundled Noto Sans Egyptian Hieroglyphs font (OFL), for quadrat layout.

    Requires fontTools and brotli (build time only): pip install fonttools brotli
    """
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    font = TTFont(str(font_path))
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    upem = font["head"].unitsPerEm
    metrics = {}
    for cp, name in cmap.items():
        if not (0x13000 <= cp <= 0x143FF):
            continue
        pen = BoundsPen(glyph_set)
        glyph_set[name].draw(pen)
        if pen.bounds is None:
            continue
        x_min, y_min, x_max, y_max = pen.bounds
        metrics[f"{cp:X}"] = [round(x_min), round(y_min), round(x_max), round(y_max), round(glyph_set[name].width)]
    out = OUT.parent / "glyph_metrics.json.gz"
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        json.dump({"font": font_path.name, "units_per_em": upem, "glyphs": metrics}, handle, separators=(",", ":"))
    print(f"{len(metrics)} glyph boxes -> {out}")
    return out
