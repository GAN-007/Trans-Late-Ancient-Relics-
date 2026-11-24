"""Period-aware Egyptian grammar: which forms belong to which stage of the language.

Egyptian changed from a synthetic language (Old and Middle Egyptian: sḏm.n=f, no article) to an
analytic one (Late Egyptian, Demotic, Coptic: definite article, periphrastic tenses). Each feature
below lists the stages where it is productive, with the grammar that documents it. The detector
finds features in a transliteration and says which stages are consistent with them, flagging
anachronisms (a Late Egyptian negation in an Old Kingdom text, for example).

References: A. H. Gardiner, Egyptian Grammar (3rd ed. 1957); J. P. Allen, Middle Egyptian (3rd ed.
2014) and The Ancient Egyptian Language (2013); E. Edel, Altägyptische Grammatik (1955/64);
F. Junge, Late Egyptian Grammar (2005); J. H. Johnson, Thus Wrote ʿOnchsheshonqy (Demotic, 3rd ed.
2000); B. Layton, A Coptic Grammar (3rd ed. 2011); A. Loprieno, Ancient Egyptian (1995).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

STAGES = ["old_egyptian", "middle_egyptian", "late_egyptian", "demotic", "coptic"]
STAGE_NAMES = {"old_egyptian": "Old Egyptian (c. 2600-2000 BCE)", "middle_egyptian": "Middle Egyptian (c. 2000-1300 BCE; classical later)",
               "late_egyptian": "Late Egyptian (c. 1350-700 BCE)", "demotic": "Demotic (c. 650 BCE-450 CE)", "coptic": "Coptic (c. 250-1100 CE)"}

FEATURES: list[dict[str, Any]] = [
    {"id": "sdm_n_f", "label": "sḏm.n=f (perfect / past relative)", "stages": ["old_egyptian", "middle_egyptian"],
     "pattern": r"\b[\wꜣꜥḥḫẖšṯḏ]+\.n(?:[.=][jkfsn]|[.=]ṯ|[.=]sn|[.=]ṯn|\s)", "ref": "Gardiner §§ 411-422; Junge 2005 § 3.2 (replaced in Late Egyptian)",
     "note": "Lost from the spoken language in the New Kingdom; Late Egyptian uses sḏm=f / jr=f sḏm for the past."},
    {"id": "contingent", "label": "contingent sḏm.jn=f / sḏm.ḫr=f / sḏm.kꜣ=f", "stages": ["old_egyptian", "middle_egyptian"],
     "pattern": r"\.(?:jn|ḫr|kꜣ)[.=]", "ref": "Gardiner §§ 425-434"},
    {"id": "old_independent_pronoun", "label": "Old Egyptian independent pronouns twt, ṯmt, swt, stt", "stages": ["old_egyptian"],
     "pattern": r"\b(?:twt|ṯmt|swt|stt)\b", "ref": "Edel §§ 164-171; Allen 2013 § 4.3",
     "note": "Middle Egyptian replaced them with ntk, ntṯ, ntf, nts."},
    {"id": "middle_independent_pronoun", "label": "independent pronouns ntk, ntṯ, ntf, nts, ntsn", "stages": ["middle_egyptian"],
     "pattern": r"\b(?:ntk|ntṯ|ntf|nts|ntṯn|ntsn)\b", "ref": "Gardiner § 64"},
    {"id": "late_independent_pronoun", "label": "Late Egyptian independent pronouns mntk, mntf, mnts, mntw", "stages": ["late_egyptian", "demotic"],
     "pattern": r"\b(?:mntk|mntt|mntf|mnts|mnttn|mntw)\b", "ref": "Junge 2005 § 2.1.3", "note": "Coptic ⲛⲧⲟⲕ, ⲛⲧⲟϥ continue them."},
    {"id": "z_s_distinct", "label": "z kept distinct from s", "stages": ["old_egyptian"], "pattern": r"z",
     "ref": "Allen 2013 § 3.4; Edel § 116", "note": "z and s merged in Middle Egyptian, which writes both as s."},
    {"id": "definite_article", "label": "definite article pꜣ / tꜣ / nꜣ", "stages": ["late_egyptian", "demotic", "coptic"],
     "pattern": r"\b(?:pꜣ|tꜣ|nꜣ)\s+(?!n\b)", "ref": "Junge 2005 § 2.2.1; Layton § 40",
     "note": "Earlier Egyptian has no article; pꜣ is a demonstrative 'this'. The article begins in Late Egyptian (Coptic ⲡ-, ⲧ-, ⲛ-)."},
    {"id": "first_present", "label": "First Present / pseudoverbal ḥr + infinitive (jw=f ḥr sḏm, tw=j ḥr sḏm)", "stages": ["middle_egyptian", "late_egyptian", "demotic", "coptic"],
     "pattern": r"\bḥr\s+[\wꜣꜥḥḫẖšṯḏ]+", "ref": "Gardiner §§ 320-330; Junge 2005 § 4.1; Layton § 306 (Coptic ϥⲥⲱⲧⲙ̄)"},
    {"id": "late_negation_bn", "label": "negation bn / bw", "stages": ["late_egyptian", "demotic"], "pattern": r"\b(?:bn|bw)\b",
     "ref": "Junge 2005 § 3.6", "note": "Earlier Egyptian negates with n and nn; Coptic with ⲛ̄ … ⲁⲛ and ⲙⲡⲉ-."},
    {"id": "early_negation_nn", "label": "negation nn", "stages": ["old_egyptian", "middle_egyptian"], "pattern": r"\bnn\b",
     "ref": "Gardiner §§ 103-110"},
    {"id": "late_perfect_jr", "label": "periphrastic perfect jr=f sḏm", "stages": ["late_egyptian", "demotic"],
     "pattern": r"\bjr[.=][jkfs]\s+[\wꜣꜥḥḫẖšṯḏ]+", "ref": "Junge 2005 § 3.3", "note": "The ancestor of the Coptic perfect ⲁϥⲥⲱⲧⲙ̄."},
    {"id": "late_suffix_3pl", "label": "3rd plural suffix =w", "stages": ["late_egyptian", "demotic"], "pattern": r"=w\b",
     "ref": "Junge 2005 § 2.1.1", "note": "Earlier Egyptian writes .sn; Coptic =ⲟⲩ."},
    {"id": "early_suffix_3pl", "label": "3rd plural suffix .sn", "stages": ["old_egyptian", "middle_egyptian"], "pattern": r"[.=]sn\b",
     "ref": "Gardiner § 34"},
    {"id": "stative", "label": "stative (old perfective) sḏm.kw / .tj / .w", "stages": ["old_egyptian", "middle_egyptian", "late_egyptian", "demotic", "coptic"],
     "pattern": r"\.(?:kw|kj|tj|tw)\b", "ref": "Gardiner §§ 309-317; Layton § 160 (Coptic qualitative)"},
]
_COMPILED = [(f, re.compile(f["pattern"])) for f in FEATURES]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip()).replace("i̯", "j").replace("ı͗", "j").replace("ꞽ", "j")


def detect(transliteration: str, period: str | None = None) -> dict[str, Any]:
    """Grammatical features in a transliteration, the stages they fit, and anachronisms for a claimed period."""
    text = _norm(transliteration)
    found = []
    for feature, rx in _COMPILED:
        hits = sorted(set(m.group(0).strip() for m in rx.finditer(text)))
        if hits:
            found.append({"feature": feature["id"], "label": feature["label"], "matches": hits[:5],
                          "stages": feature["stages"], "reference": feature["ref"], "note": feature.get("note")})
    # z/s is evidence only when z actually appears; it is not counter-evidence when absent
    consistent = [s for s in STAGES if all(s in f["stages"] for f in found)] if found else list(STAGES)
    out: dict[str, Any] = {"features": found, "consistent_stages": consistent,
                           "consistent_stage_names": [STAGE_NAMES[s] for s in consistent]}
    if not found:
        out["note"] = "No period-diagnostic forms were found; the text could belong to several stages."
    elif not consistent:
        out["note"] = ("The forms come from different stages. That happens in archaizing texts (e.g. Middle Egyptian used "
                       "for monuments in the Late Period) and in mixed registers; check the date of the object.")
    if period:
        if period not in STAGES:
            raise ValueError(f"period must be one of {', '.join(STAGES)}")
        out["period"] = period
        out["anachronisms"] = [{"feature": f["feature"], "label": f["label"], "matches": f["matches"],
                                "belongs_to": f["stages"], "reference": f["reference"]}
                               for f in found if period not in f["stages"]]
    return out


def inventory(stage: str | None = None) -> list[dict[str, Any]]:
    rows = [{k: v for k, v in f.items() if k != "pattern"} for f in FEATURES]
    return [r for r in rows if not stage or stage in r["stages"]]


# ------------------------------------------------------------------ TLA morphological glosses
GLOSS_POS = {"V": "verb", "N": "noun", "ADJ": "adjective", "PREP": "preposition", "PTCL": "particle", "PRON": "pronoun",
             "ADV": "adverb", "NUM": "numeral", "INTJ": "interjection", "PN": "personal name", "TITL": "title", "GN": "divine name",
             "ROYLN": "royal name", "TOPN": "place name", "DEM": "demonstrative", "REL": "relative", "CONJ": "conjunction"}
GLOSS_FEATURES = {"sg": "singular", "du": "dual", "pl": "plural", "m": "masculine", "f": "feminine", "1": "1st person",
                  "2": "2nd person", "3": "3rd person", "act": "active", "pass": "passive", "pfv": "perfective",
                  "ipfv": "imperfective", "prosp": "prospective", "stpr": "stative / pseudoparticiple", "inf": "infinitive",
                  "ptcp": "participle", "rel": "relative form", "impv": "imperative", "neg": "negatival complement",
                  "compl": "complementary infinitive", "nmlz": "nominalized", "emph": "emphatic", "advz": "adverbialized",
                  "spec": "specific", "post": "posterior", "nom": "nominal", "subj": "subjunctive", "cntg": "contingent",
                  "tam": "tense-aspect-mood", "def": "definite", "art": "article", "poss": "possessive", "Q": "interrogative"}


def explain_gloss(gloss: str) -> dict[str, Any]:
    """Explain a TLA Leipzig-style morphological gloss: 'V\\tam.act:stpr.1sg', 'N.f:sg', '=3sg.m'."""
    gloss = (gloss or "").strip()
    if not gloss:
        return {"gloss": gloss, "parts": []}
    suffix = gloss.startswith("=")
    head, _, rest = gloss.lstrip("=").partition("\\")
    pos_code = re.split(r"[.:]", head)[0]
    pieces = re.findall(r"[A-Za-z]+|\d", gloss.lstrip("=").replace(pos_code, "", 1) if not suffix else gloss[1:])
    features = []
    for piece in pieces:
        if piece in GLOSS_FEATURES:
            features.append(GLOSS_FEATURES[piece])
        else:
            m = re.fullmatch(r"(\d)(sg|du|pl)", piece)
            if m:
                features += [GLOSS_FEATURES[m.group(1)], GLOSS_FEATURES[m.group(2)]]
    m = re.search(r"(\d)(sg|du|pl)", gloss)
    if m and GLOSS_FEATURES[m.group(1)] not in features:
        features += [GLOSS_FEATURES[m.group(1)], GLOSS_FEATURES[m.group(2)]]
    pos = "suffix pronoun" if suffix else GLOSS_POS.get(pos_code, pos_code)
    return {"gloss": gloss, "part_of_speech": pos, "features": list(dict.fromkeys(features)),
            "reading": f"{pos}" + (f" ({', '.join(dict.fromkeys(features))})" if features else "")}
