"""Quadrat (sign group) parser and layout renderer for Egyptian hieroglyphic text.

Hieroglyphs are written in groups ("quadrats") stacked and juxtaposed inside an imaginary
square. Two encodings describe that layout and both are parsed into the same tree:

* Unicode format controls (Unicode 15+ Egyptian hieroglyph grammar): vertical joiner U+13430,
  horizontal joiner U+13431, the corner/middle insertion controls, overlay U+13436, segment
  brackets U+13437/U+13438, enclosures U+1343C-U+1343F, mirror U+13440, blanks and lost-sign
  placeholders U+13441-U+13446 and damage modifiers U+13447-U+13455.
* Manuel de Codage (MdC), the encoding used by JSesh and the TLA: "-" separates quadrats,
  ":" stacks, "*" juxtaposes, "(...)" groups, "&" ligatures, "\\" mirrors, "<...>" cartouches,
  "//" a lost quadrat, "#b ... #e" damaged (shaded) signs.

The tree serializes back to either encoding and lays out as SVG using the real glyph boxes of
the bundled Noto Sans Egyptian Hieroglyphs font.
"""
from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import signs as sign_catalog
from .egyptian import UNILITERALS

VJ, HJ, OVERLAY = "\U00013430", "\U00013431", "\U00013436"
BEGIN_SEG, END_SEG = "\U00013437", "\U00013438"
INSERTS = {"\U00013432": "top_start", "\U00013433": "bottom_start", "\U00013434": "top_end", "\U00013435": "bottom_end",
           "\U00013439": "middle", "\U0001343A": "top", "\U0001343B": "bottom"}
INSERT_CHARS = {v: k for k, v in INSERTS.items()}
ENCLOSURE_OPEN = {"\U0001343C": "enclosure", "\U0001343E": "walled_enclosure"}
ENCLOSURE_CLOSE = {"\U0001343D": "enclosure", "\U0001343F": "walled_enclosure"}
MIRROR = "\U00013440"
PLACEHOLDERS = {"\U00013441": ("blank", 1.0, 1.0), "\U00013442": ("blank", 0.5, 0.5), "\U00013443": ("lost", 1.0, 1.0),
                "\U00013444": ("lost", 0.5, 0.5), "\U00013445": ("lost", 0.5, 1.0), "\U00013446": ("lost", 1.0, 0.5)}
DAMAGE = {0x13447 + i: name for i, name in enumerate([
    {"ts"}, {"bs"}, {"ts", "bs"}, {"te"}, {"ts", "te"}, {"bs", "te"}, {"ts", "bs", "te"}, {"be"},
    {"ts", "be"}, {"bs", "be"}, {"ts", "bs", "be"}, {"te", "be"}, {"ts", "te", "be"}, {"bs", "te", "be"}, {"ts", "bs", "te", "be"}])}
CARTOUCHE_START, CARTOUCHE_END = "\U00013379", "\U0001337A"  # V011A / V011B


class QuadratError(ValueError):
    pass


@dataclass
class Node:
    kind: str  # sign | horizontal | vertical | insertion | overlay | enclosure | placeholder
    children: list["Node"] = field(default_factory=list)
    glyph: str = ""
    code: str = ""
    mirrored: bool = False
    damage: list[str] = field(default_factory=list)
    position: str = ""   # insertion corner for an inserted child
    style: str = ""      # enclosure style / placeholder kind
    size: tuple[float, float] = (1.0, 1.0)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.kind == "sign":
            record = sign_catalog.sign(self.glyph) if self.glyph else None
            out.update(glyph=self.glyph, code=self.code or (record or {}).get("gardiner") or "",
                       values=(record or {}).get("values", []))
            if self.mirrored:
                out["mirrored"] = True
            if self.damage:
                out["damage"] = sorted(self.damage)
        if self.position:
            out["position"] = self.position
        if self.style:
            out["style"] = self.style
        if self.kind == "placeholder":
            out["size"] = list(self.size)
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        return out


# ------------------------------------------------------------------ Unicode parser
class _UnicodeParser:
    def __init__(self, text: str):
        self.items = [c for c in text if not c.isspace()]
        self.i = 0

    def peek(self) -> str | None:
        return self.items[self.i] if self.i < len(self.items) else None

    def take(self) -> str:
        char = self.items[self.i]
        self.i += 1
        return char

    def fragment(self, stop: set[str] | None = None) -> list[Node]:
        groups = []
        while self.peek() is not None and (stop is None or self.peek() not in stop):
            groups.append(self.vertical())
        return groups

    def vertical(self) -> Node:
        parts = [self.horizontal()]
        while self.peek() == VJ:
            self.take()
            parts.append(self.horizontal())
        return parts[0] if len(parts) == 1 else Node("vertical", parts)

    def horizontal(self) -> Node:
        parts = [self.horizontal_part()]
        while self.peek() == HJ:
            self.take()
            parts.append(self.horizontal_part())
        return parts[0] if len(parts) == 1 else Node("horizontal", parts)

    def horizontal_part(self) -> Node:
        if self.peek() == BEGIN_SEG:
            self.take()
            inner = self.vertical()
            if self.peek() != END_SEG:
                raise QuadratError("Unclosed segment (U+13437 without U+13438).")
            self.take()
            return self.with_insertions(inner)
        return self.basic()

    def basic(self) -> Node:
        char = self.peek()
        if char is None:
            raise QuadratError("A joiner or insertion control is not followed by a sign.")
        if char in ENCLOSURE_OPEN or char == CARTOUCHE_START:
            return self.enclosure()
        if char in PLACEHOLDERS:
            self.take()
            kind, w, h = PLACEHOLDERS[char]
            return Node("placeholder", style=kind, size=(w, h))
        core = self.core()
        return self.with_insertions(core)

    def core(self) -> Node:
        node = self.literal()
        if self.peek() == OVERLAY:
            self.take()
            node = Node("overlay", [node, self.literal()])
        return node

    def literal(self) -> Node:
        char = self.peek()
        if char is None or not _is_sign(char):
            raise QuadratError(f"Expected a hieroglyph, found {char!r}.")
        self.take()
        node = Node("sign", glyph=char)
        if self.peek() == MIRROR:
            self.take()
            node.mirrored = True
        if self.peek() is not None and ord(self.peek()) in DAMAGE:
            node.damage = sorted(DAMAGE[ord(self.take())])
        return node

    def with_insertions(self, base: Node) -> Node:
        inserted = []
        while self.peek() in INSERTS:
            position = INSERTS[self.take()]
            if self.peek() == BEGIN_SEG:
                self.take()
                child = self.vertical()
                if self.peek() != END_SEG:
                    raise QuadratError("Unclosed segment in an insertion.")
                self.take()
            else:
                child = self.core()
            child.position = position
            inserted.append(child)
        return Node("insertion", [base, *inserted]) if inserted else base

    def enclosure(self) -> Node:
        opening = ""
        if self.peek() == CARTOUCHE_START:
            opening = self.take()
        style = "cartouche"
        if self.peek() in ENCLOSURE_OPEN:
            style = "serekh" if ENCLOSURE_OPEN[self.take()] == "walled_enclosure" else "cartouche"
        content = self.fragment(stop=set(ENCLOSURE_CLOSE) | {CARTOUCHE_END})
        if self.peek() in ENCLOSURE_CLOSE:
            self.take()
        if self.peek() == CARTOUCHE_END:
            self.take()
        elif not opening and self.peek() is None:
            raise QuadratError("Unclosed enclosure.")
        return Node("enclosure", content, style=style)


def _is_sign(char: str) -> bool:
    cp = ord(char)
    return 0x13000 <= cp <= 0x1342F or 0x13460 <= cp <= 0x143FF


def parse_unicode(text: str) -> list[Node]:
    parser = _UnicodeParser(text)
    groups = parser.fragment()
    return groups


# ------------------------------------------------------------------ MdC parser
_MDC_UNILITERALS = {row.get("mdc", value): row["glyph"] for value, row in UNILITERALS.items() if row.get("glyph")}
_MDC_PHONETIC = {"A": "G1", "i": "M17", "y": "Z4", "a": "D36", "w": "G43", "W": "Z7", "b": "D58", "p": "Q3", "f": "I9",
                 "m": "G17", "n": "N35", "r": "D21", "h": "O4", "H": "V28", "x": "Aa1", "X": "F32", "s": "S29", "z": "O34",
                 "S": "N37", "q": "N29", "k": "V31", "g": "W11", "t": "X1", "T": "V13", "d": "D46", "D": "I10",
                 "nfr": "F35", "anx": "S34", "Htp": "R4", "pr": "O1", "ib": "F34", "nTr": "R8", "Dd": "R11", "ra": "N5",
                 "nb": "V30", "mn": "Y5", "mr": "U6", "sA": "G39", "Hm": "U36", "pt": "N1", "tA": "N16", "mw": "N35A",
                 "wsr": "F12", "xpr": "L1", "nsw": "M23", "sw": "M23"}


def resolve_code(code: str) -> str:
    """MdC/Gardiner code (A1, Aa28, n, nfr) -> glyph."""
    if code in _MDC_PHONETIC:
        code = _MDC_PHONETIC[code]
    record = sign_catalog.sign(code)
    if record:
        return record["glyph"]
    if code in _MDC_UNILITERALS:
        return _MDC_UNILITERALS[code]
    raise QuadratError(f"Unknown sign code '{code}'.")


_MDC_TOKEN = re.compile(r"\s*(//|#b|#e|\\\\?\d*|[-:*()&<>!]|[A-Za-z][A-Za-z0-9]*|[\U00013000-\U000143FF])")


def _mdc_tokens(text: str) -> list[str]:
    tokens, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = _MDC_TOKEN.match(text, pos)
        if not m:
            raise QuadratError(f"Cannot read Manuel de Codage at '{text[pos:pos + 10]}'.")
        tokens.append(m.group(1))
        pos = m.end()
    return [t for t in tokens if t and t != "!"]


class _MdcParser:
    def __init__(self, text: str):
        self.tokens = _mdc_tokens(text)
        self.i = 0
        self.damaged = False

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self) -> str:
        token = self.tokens[self.i]
        self.i += 1
        return token

    def fragment(self, stop: str | None = None) -> list[Node]:
        groups = []
        while self.peek() is not None and self.peek() != stop:
            if self.peek() == "-":
                self.take()
                continue
            if self.peek() in {"#b", "#e"}:
                self.damaged = self.take() == "#b"
                continue
            groups.append(self.vertical())
        return groups

    def vertical(self) -> Node:
        parts = [self.horizontal()]
        while self.peek() == ":":
            self.take()
            parts.append(self.horizontal())
        return parts[0] if len(parts) == 1 else Node("vertical", parts)

    def horizontal(self) -> Node:
        parts = [self.atom()]
        while self.peek() in {"*", "&"}:
            joiner = self.take()
            nxt = self.atom()
            if joiner == "&":
                parts[-1] = Node("overlay", [parts[-1], nxt])
            else:
                parts.append(nxt)
        return parts[0] if len(parts) == 1 else Node("horizontal", parts)

    def atom(self) -> Node:
        token = self.peek()
        if token is None:
            raise QuadratError("Unexpected end of Manuel de Codage.")
        while token in {"#b", "#e"}:
            self.damaged = self.take() == "#b"
            token = self.peek()
        if token == "(":
            self.take()
            inner = self.vertical()
            if self.peek() != ")":
                raise QuadratError("Unclosed '(' in Manuel de Codage.")
            self.take()
            return inner
        if token == "<":
            self.take()
            content = self.fragment(stop=">")
            if self.peek() != ">":
                raise QuadratError("Unclosed cartouche '<'.")
            self.take()
            return Node("enclosure", content, style="cartouche")
        if token == "//":
            self.take()
            return Node("placeholder", style="lost", size=(1.0, 1.0))
        self.take()
        glyph = token if len(token) == 1 and _is_sign(token) else resolve_code(token)
        node = Node("sign", glyph=glyph, code="" if glyph == token else token)
        if self.peek() and self.peek().startswith("\\"):
            self.take()
            node.mirrored = True
        if self.damaged:
            node.damage = ["ts", "bs", "te", "be"]
        return node


def parse_mdc(text: str) -> list[Node]:
    return _MdcParser(text).fragment()


def parse(text: str) -> dict[str, Any]:
    """Parse Unicode (with format controls) or MdC into quadrat groups."""
    text = (text or "").strip()
    if not text:
        raise QuadratError("Enter hieroglyphs or Manuel de Codage.")
    encoding = "unicode" if any(_is_sign(c) or 0x13430 <= ord(c) <= 0x1345F for c in text) and not re.search(r"[A-Za-z]{1,3}\d", text) else "mdc"
    groups = parse_unicode(text) if encoding == "unicode" else parse_mdc(text)
    return {"encoding": encoding, "groups": groups, "tree": [g.to_dict() for g in groups],
            "unicode": to_unicode(groups), "mdc": to_mdc(groups), "sign_count": sum(_count(g) for g in groups)}


def _count(node: Node) -> int:
    return (1 if node.kind == "sign" else 0) + sum(_count(c) for c in node.children)


# ------------------------------------------------------------------ serializers
_DAMAGE_CHAR = {frozenset(v): chr(k) for k, v in DAMAGE.items()}


def to_unicode(groups: list[Node]) -> str:
    def enc(node: Node, nested: bool = False) -> str:
        if node.kind == "sign":
            out = node.glyph + (MIRROR if node.mirrored else "")
            if node.damage:
                out += _DAMAGE_CHAR.get(frozenset(node.damage), chr(0x13455))
            return out
        if node.kind == "vertical":
            body = VJ.join(enc(c, True) for c in node.children)
            return BEGIN_SEG + body + END_SEG if nested else body
        if node.kind == "horizontal":
            return HJ.join(BEGIN_SEG + enc(c) + END_SEG if c.kind == "vertical" else enc(c, True) for c in node.children)
        if node.kind == "overlay":
            return enc(node.children[0], True) + OVERLAY + enc(node.children[1], True)
        if node.kind == "insertion":
            base, *rest = node.children
            out = enc(base, True)
            for child in rest:
                inner = enc(child)
                out += INSERT_CHARS[child.position] + (BEGIN_SEG + inner + END_SEG if child.kind in {"vertical", "horizontal"} else inner)
            return out
        if node.kind == "enclosure":
            # cartouche: V011A + BEGIN ENCLOSURE … END ENCLOSURE + V011B (Unicode 15 enclosure model)
            opener, closer = ("\U0001343E", "\U0001343F") if node.style == "serekh" else (CARTOUCHE_START + "\U0001343C", "\U0001343D" + CARTOUCHE_END)
            return opener + "".join(enc(c) for c in node.children) + closer
        if node.kind == "placeholder":
            for char, (kind, w, h) in PLACEHOLDERS.items():
                if kind == node.style and (w, h) == tuple(node.size):
                    return char
        return ""
    return "".join(enc(g) for g in groups)


def to_mdc(groups: list[Node]) -> str:
    def code(node: Node) -> str:
        record = sign_catalog.sign(node.glyph)
        return node.code or (record or {}).get("gardiner") or (record or {}).get("unikemet_code") or node.glyph

    def enc(node: Node, nested: bool = False) -> str:
        if node.kind == "sign":
            out = code(node) + ("\\" if node.mirrored else "")
            return f"#b-{out}-#e" if node.damage and not nested else out
        if node.kind == "vertical":
            body = ":".join(enc(c, True) for c in node.children)
            return f"({body})" if nested else body
        if node.kind == "horizontal":
            body = "*".join(enc(c, True) for c in node.children)
            return f"({body})" if nested else body
        if node.kind == "overlay":
            return "&".join(enc(c, True) for c in node.children)
        if node.kind == "insertion":
            return "*".join(enc(c, True) for c in node.children)  # MdC has no corner insertion; juxtapose
        if node.kind == "enclosure":
            return "<-" + "-".join(enc(c) for c in node.children) + "->"
        if node.kind == "placeholder":
            return "//" if node.style == "lost" else "."
        return ""
    return "-".join(enc(g) for g in groups)


# ------------------------------------------------------------------ layout
@lru_cache(maxsize=1)
def _metrics() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "signs" / "glyph_metrics.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _natural(glyph: str) -> tuple[float, float, list[int] | None]:
    data = _metrics()
    box = data["glyphs"].get(f"{ord(glyph):X}")
    if not box:
        return 0.8, 0.8, None
    upem = data["units_per_em"]
    x_min, y_min, x_max, y_max, _ = box
    return max(1, x_max - x_min) / upem, max(1, y_max - y_min) / upem, box


@dataclass
class Placed:
    glyph: str
    x: float
    y: float
    w: float
    h: float
    box: list[int] | None
    mirrored: bool = False
    damage: list[str] = field(default_factory=list)


GAP = 0.06


def _size(node: Node) -> tuple[float, float]:
    """Natural size of a group, in em, before fitting."""
    if node.kind == "sign":
        w, h, _ = _natural(node.glyph)
        return w, h
    if node.kind == "placeholder":
        return node.size
    sizes = [_size(c) for c in node.children]
    if node.kind == "horizontal":
        return sum(w for w, _ in sizes) + GAP * (len(sizes) - 1), max(h for _, h in sizes)
    if node.kind == "vertical":
        return max(w for w, _ in sizes), sum(h for _, h in sizes) + GAP * (len(sizes) - 1)
    if node.kind in {"overlay", "insertion"}:
        return sizes[0] if node.kind == "insertion" else (max(w for w, _ in sizes), max(h for _, h in sizes))
    if node.kind == "enclosure":
        inner_w = sum(w for w, _ in sizes) + GAP * max(0, len(sizes) - 1)
        return inner_w + 0.5, max((h for _, h in sizes), default=1.0) + 0.3
    return 1.0, 1.0


def _layout(node: Node, x: float, y: float, w: float, h: float, out: list, frames: list) -> None:
    nw, nh = _size(node)
    scale = min(w / nw if nw else 1, h / nh if nh else 1, 1.0 if node.kind == "sign" else 10.0)
    fw, fh = nw * scale, nh * scale
    ox, oy = x + (w - fw) / 2, y + (h - fh) / 2
    if node.kind == "sign":
        _, _, box = _natural(node.glyph)
        out.append(Placed(node.glyph, ox, oy, fw, fh, box, node.mirrored, node.damage))
    elif node.kind == "placeholder":
        frames.append({"type": node.style, "x": ox, "y": oy, "w": fw, "h": fh})
    elif node.kind == "horizontal":
        cx = ox
        for child in node.children:
            cw, _ = _size(child)
            _layout(child, cx, oy, cw * scale, fh, out, frames)
            cx += cw * scale + GAP * scale
    elif node.kind == "vertical":
        cy = oy
        for child in node.children:
            _, ch = _size(child)
            _layout(child, ox, cy, fw, ch * scale, out, frames)
            cy += ch * scale + GAP * scale
    elif node.kind == "overlay":
        for child in node.children:
            _layout(child, ox, oy, fw, fh, out, frames)
    elif node.kind == "insertion":
        base, *rest = node.children
        _layout(base, ox, oy, fw, fh, out, frames)
        for child in rest:
            iw, ih = fw * 0.5, fh * 0.5
            px = {"top_start": ox, "bottom_start": ox, "top_end": ox + fw - iw, "bottom_end": ox + fw - iw}.get(child.position, ox + (fw - iw) / 2)
            py = {"top_start": oy, "top_end": oy, "top": oy, "bottom_start": oy + fh - ih, "bottom_end": oy + fh - ih,
                  "bottom": oy + fh - ih}.get(child.position, oy + (fh - ih) / 2)
            _layout(child, px, py, iw, ih, out, frames)
    elif node.kind == "enclosure":
        frames.append({"type": node.style, "x": ox, "y": oy, "w": fw, "h": fh})
        inner = Node("horizontal", node.children) if len(node.children) > 1 else node.children[0]
        _layout(inner, ox + 0.25 * scale, oy + 0.15 * scale, fw - 0.5 * scale, fh - 0.3 * scale, out, frames)


def layout(groups: list[Node], direction: str = "ltr") -> dict[str, Any]:
    """Place each quadrat in a 1 em square (wider for cartouches) along a line."""
    placed: list[Placed] = []
    frames: list[dict[str, Any]] = []
    x = 0.0
    for group in groups:
        nw, nh = _size(group)
        width = max(1.0, nw / nh) if group.kind == "enclosure" else 1.0
        _layout(group, x, 0.0, width, 1.0, placed, frames)
        x += width + 0.12
    total = max(x - 0.12, 0.0)
    if direction == "rtl":
        for p in placed:
            p.x, p.mirrored = total - p.x - p.w, not p.mirrored
        for f in frames:
            f["x"] = total - f["x"] - f["w"]
    return {"width": total, "height": 1.0, "signs": placed, "frames": frames}


def render_svg(text: str, direction: str = "ltr", size: int = 64) -> dict[str, Any]:
    """Parse and render as an SVG string (uses the Noto Sans Egyptian Hieroglyphs web font)."""
    parsed = parse(text)
    laid = layout(parsed["groups"], direction)
    upem = _metrics()["units_per_em"]
    pad = 0.1
    width, height = laid["width"] + 2 * pad, laid["height"] + 2 * pad
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-pad:.3f} {-pad:.3f} {width:.3f} {height:.3f}" '
             f'width="{width * size:.0f}" height="{height * size:.0f}" role="img" aria-label="Hieroglyphic text">',
             '<defs><pattern id="hatch" width="0.08" height="0.08" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
             '<line x1="0" y1="0" x2="0" y2="0.08" stroke="#8a6a3a" stroke-width="0.02"/></pattern></defs>']
    for frame in laid["frames"]:
        x, y, w, h = frame["x"], frame["y"], frame["w"], frame["h"]
        if frame["type"] == "cartouche":
            parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{h / 2:.3f}" fill="none" stroke="currentColor" stroke-width="0.03"/>')
        elif frame["type"] == "serekh":
            parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="none" stroke="currentColor" stroke-width="0.03"/>')
        elif frame["type"] == "lost":
            parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="url(#hatch)" stroke="#8a6a3a" stroke-width="0.01"/>')
    for p in laid["signs"]:
        if p.box:
            x_min, y_min, x_max, y_max, _ = p.box
            s = min(p.w / max(1, x_max - x_min), p.h / max(1, y_max - y_min))
            tx, ty = p.x - x_min * s, p.y + y_max * s
            if p.mirrored:
                transform = f"matrix({-s:.6f},0,0,{s:.6f},{p.x + p.w + x_min * s:.4f},{ty:.4f})"
            else:
                transform = f"matrix({s:.6f},0,0,{s:.6f},{tx:.4f},{ty:.4f})"
            parts.append(f'<text font-family="Noto Sans Egyptian Hieroglyphs" font-size="{upem}" transform="{transform}">{p.glyph}</text>')
        else:
            parts.append(f'<text font-family="Noto Sans Egyptian Hieroglyphs, serif" font-size="{p.h:.3f}" x="{p.x:.3f}" y="{p.y + p.h * 0.85:.3f}">{p.glyph}</text>')
        if p.damage:
            for corner in p.damage:
                dx = p.x if corner.endswith("s") else p.x + p.w / 2
                dy = p.y if corner.startswith("t") else p.y + p.h / 2
                parts.append(f'<rect x="{dx:.3f}" y="{dy:.3f}" width="{p.w / 2:.3f}" height="{p.h / 2:.3f}" fill="url(#hatch)" opacity="0.8"/>')
    parts.append("</svg>")
    missing = sorted({p.glyph for p in laid["signs"] if not p.box})
    return {**{k: v for k, v in parsed.items() if k != "groups"}, "svg": "".join(parts), "direction": direction,
            "signs_without_font_glyph": missing,
            "note": "Layout follows the Unicode quadrat model with real glyph proportions; signs only in Extended-A have no font glyph yet and are drawn as placeholders."
            if missing else "Layout follows the Unicode quadrat model with real glyph proportions."}
