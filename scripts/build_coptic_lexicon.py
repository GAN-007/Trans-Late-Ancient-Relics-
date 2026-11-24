"""Build app/data/coptic/ccl.json.gz from the Comprehensive Coptic Lexicon (TEI XML).

Source: Comprehensive Coptic Lexicon: Including Loanwords from Ancient Greek, v1.2 (2020),
BBAW "Strukturen und Transformationen des Wortschatzes der ägyptischen Sprache" and FU Berlin
DDGLC; CC BY-SA 4.0, DOI 10.17169/refubium-2333. The XML is distributed with the Coptic
Dictionary Online (github.com/KELLIA/dictionary, xml/Comprehensive_Coptic_Lexicon-v1.2-2020.xml).

    python scripts/build_coptic_lexicon.py path/to/Comprehensive_Coptic_Lexicon-v1.2-2020.xml
"""
from __future__ import annotations

import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "coptic" / "ccl.json.gz"


def text(el) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def entry_record(entry) -> dict:
    forms = []
    for form in entry.findall(f"{TEI}form"):
        if "#deprecated" in (form.get("change") or ""):
            continue
        orth = text(form.find(f"{TEI}orth"))
        if not orth:
            continue
        dialects = [text(u) for u in form.findall(f"{TEI}usg") if u.get("type") == "geo"]
        forms.append({"orth": orth, "dialects": dialects, "type": form.get("type") or "form"})
    gram = entry.find(f"{TEI}gramGrp")
    senses = []
    for sense in entry.findall(f"{TEI}sense"):
        for cit in sense.findall(f"{TEI}cit"):
            quotes = {q.get(XML_LANG): text(q) for q in cit.findall(f"{TEI}quote") if text(q)}
            if quotes:
                senses.append({**quotes, "bibl": text(cit.find(f"{TEI}bibl"))})
    etym = {}
    for e in entry.findall(f"{TEI}etym"):
        for ref in e.iter(f"{TEI}ref"):
            kind, target = ref.get("type"), (ref.get("target") or "").lstrip("#")
            if kind == "WCNae":
                etym.setdefault("egyptian_tla", []).append(target)
            elif kind == "WCNde":
                etym.setdefault("demotic_tla", []).append(target)
            elif kind == "Greek":
                etym.setdefault("greek", []).append(text(ref))
            elif kind == "greek_lemma::grl_lemma":
                etym.setdefault("greek", []).append(text(ref))
        note = text(e.find(f"{TEI}note"))
        if note:
            etym["note"] = note
    return {"id": entry.get(XML_ID), "type": entry.get("type") or "", "forms": forms,
            "pos": text(gram.find(f"{TEI}pos")) if gram is not None else "",
            "gender": text(gram.find(f"{TEI}gen")) if gram is not None else "",
            "senses": senses, "etym": etym}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    root = ET.parse(sys.argv[1]).getroot()
    entries = [entry_record(e) for e in root.iter(f"{TEI}entry")]
    entries = [e for e in entries if e["id"] and e["forms"]]
    data = {"source": "Comprehensive Coptic Lexicon v1.2 (2020)", "license": "CC BY-SA 4.0",
            "doi": "10.17169/refubium-2333", "citation": "Burns, Feder, John, Kupreyev et al., Comprehensive Coptic Lexicon: "
            "Including Loanwords from Ancient Greek, v1.2, BBAW / FU Berlin 2020.", "count": len(entries), "entries": entries}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(entries)} entries -> {OUT}")


if __name__ == "__main__":
    main()
