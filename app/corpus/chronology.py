"""Egyptian chronology: period and dynasty labels -> approximate year ranges and language stages.

Dates are astronomical years (negative = BCE) after E. Hornung, R. Krauss and D. A. Warburton (eds.),
Ancient Egyptian Chronology, Leiden 2006; dates before c. 2000 BCE carry decades of uncertainty.
Labels are matched in English and in the German used by the Thesaurus Linguae Aegyptiae.
"""
from __future__ import annotations

import re
from typing import Any

CITATION = "Hornung, Krauss & Warburton (eds.), Ancient Egyptian Chronology, Leiden 2006 (approximate)"

DYNASTIES: dict[int, tuple[int, int]] = {
    0: (-3200, -2900), 1: (-2900, -2730), 2: (-2730, -2590), 3: (-2592, -2544), 4: (-2543, -2436), 5: (-2435, -2306),
    6: (-2305, -2118), 7: (-2150, -2118), 8: (-2150, -2118), 9: (-2118, -1980), 10: (-2118, -1980), 11: (-2080, -1940),
    12: (-1939, -1760), 13: (-1759, -1630), 14: (-1700, -1630), 15: (-1630, -1520), 16: (-1650, -1540), 17: (-1650, -1540),
    18: (-1539, -1292), 19: (-1292, -1191), 20: (-1190, -1077), 21: (-1076, -944), 22: (-943, -746), 23: (-880, -730),
    24: (-735, -715), 25: (-722, -655), 26: (-664, -525), 27: (-525, -404), 28: (-404, -399), 29: (-399, -380),
    30: (-380, -343), 31: (-342, -332),
}
PERIODS: list[tuple[tuple[str, ...], tuple[int, int]]] = [
    (("predynastic", "prädynastisch", "naqada", "vorgeschichte"), (-4000, -3000)),
    (("early dynastic", "frühzeit", "thinit"), (-2900, -2590)),
    (("old kingdom", "altes reich"), (-2592, -2118)),
    (("first intermediate", "1. zwischenzeit", "erste zwischenzeit"), (-2118, -1980)),
    (("middle kingdom", "mittleres reich"), (-1980, -1760)),
    (("second intermediate", "2. zwischenzeit", "zweite zwischenzeit"), (-1759, -1539)),
    (("new kingdom", "neues reich"), (-1539, -1077)),
    (("ramesside", "ramessiden"), (-1292, -1077)),
    (("third intermediate", "3. zwischenzeit", "dritte zwischenzeit"), (-1076, -664)),
    (("late period", "spätzeit"), (-664, -332)),
    (("ptolemaic", "ptolemäer", "ptolemäisch"), (-332, -30)),
    (("greco-roman", "griechisch-römisch"), (-332, 395)),
    (("roman", "römisch", "römerzeit"), (-30, 395)),
    (("byzantine", "byzantinisch", "koptische zeit"), (395, 641)),
]

# Written language stages (overlapping; Middle Egyptian stayed in monumental use for millennia).
STAGES: list[tuple[str, int, int]] = [
    ("archaic_egyptian", -3300, -2600), ("old_egyptian", -2600, -2000), ("middle_egyptian", -2000, -1300),
    ("late_egyptian", -1350, -700), ("demotic", -650, 450), ("coptic", 250, 1300),
]


def date_range(label: str | None) -> tuple[int, int] | None:
    """'6. Dynastie' / 'Dynasty 12' / 'Neues Reich' / '18th Dynasty' -> (from, to) or None."""
    if not label:
        return None
    text = label.lower()
    m = re.search(r"(\d{1,2})\.\s*dyn|dynasty\s*(\d{1,2})|(\d{1,2})(?:st|nd|rd|th)\s+dynasty", text)
    if m:
        number = int(next(g for g in m.groups() if g))
        return DYNASTIES.get(number)
    for names, span in PERIODS:
        if any(name in text for name in names):
            return span
    return None


def stages_for(date_from: int | None, date_to: int | None) -> list[str]:
    if date_from is None or date_to is None:
        return []
    return [name for name, start, end in STAGES if date_from <= end and date_to >= start]


def describe(date_from: int | None, date_to: int | None) -> dict[str, Any] | None:
    if date_from is None or date_to is None:
        return None
    fmt = lambda y: f"{-y} BCE" if y < 0 else f"{y} CE"
    return {"from": date_from, "to": date_to, "label": f"c. {fmt(date_from)} – {fmt(date_to)}",
            "stages": stages_for(date_from, date_to), "basis": CITATION}
