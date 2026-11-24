"""Source-attested lemma / sense / attestation database with provenance.

Every lemma belongs to a source and has a status: attested (from a corpus or dictionary of
the language's own texts), teaching (the app's learner lexicon, not yet linked to an
attestation) or reconstructed. Attestations tie a lemma to a sentence, a text and an object,
with line, date, script, genre, find spot and bibliography, so every claim can be traced.

Importers:
* Thesaurus Linguae Aegyptiae (TLA) BTS JSON records (lemma, sentence, text, object, thesaurus),
  as served by the TLA API and in its software repositories; and the flat TLA JSONL release
  (one sentence per line with lemmatization, glossing, translation and dates).
* Comprehensive Coptic Lexicon (BBAW/FU Berlin, CC BY-SA 4.0) from app/data/coptic/ccl.json.gz.
* The app's own teaching lexicon (status "teaching").

The SQL is portable: it runs on SQLite and, through app.storage, on PostgreSQL.
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..runtime import transaction, connect
from . import chronology

DATA = Path(__file__).resolve().parent.parent / "data"
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS corpus_sources (id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
       citation TEXT, license TEXT, url TEXT, version TEXT, imported_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS corpus_lemmas (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, stage TEXT, lemma TEXT NOT NULL,
       lemma_key TEXT NOT NULL, mdc TEXT, pos TEXT, subtype TEXT, date_from INTEGER, date_to INTEGER,
       bibliography TEXT, status TEXT NOT NULL, extra TEXT)""",
    "CREATE INDEX IF NOT EXISTS corpus_lemmas_key ON corpus_lemmas(lemma_key)",
    "CREATE INDEX IF NOT EXISTS corpus_lemmas_stage ON corpus_lemmas(stage)",
    """CREATE TABLE IF NOT EXISTS corpus_forms (lemma_id TEXT NOT NULL, form TEXT NOT NULL, form_key TEXT NOT NULL,
       variety TEXT, kind TEXT, source_id TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS corpus_forms_key ON corpus_forms(form_key)",
    "CREATE INDEX IF NOT EXISTS corpus_forms_lemma ON corpus_forms(lemma_id)",
    """CREATE TABLE IF NOT EXISTS corpus_senses (lemma_id TEXT NOT NULL, lang TEXT NOT NULL, gloss TEXT NOT NULL,
       citation TEXT, source_id TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS corpus_senses_lemma ON corpus_senses(lemma_id)",
    """CREATE TABLE IF NOT EXISTS corpus_links (from_id TEXT NOT NULL, to_id TEXT NOT NULL, relation TEXT NOT NULL,
       source_id TEXT NOT NULL, note TEXT)""",
    "CREATE INDEX IF NOT EXISTS corpus_links_from ON corpus_links(from_id)",
    "CREATE INDEX IF NOT EXISTS corpus_links_to ON corpus_links(to_id)",
    """CREATE TABLE IF NOT EXISTS corpus_thesaurus (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, name TEXT, kind TEXT,
       date_from INTEGER, date_to INTEGER, reference TEXT)""",
    """CREATE TABLE IF NOT EXISTS corpus_objects (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, name TEXT, object_type TEXT,
       material TEXT, location TEXT, inventory TEXT, findspot TEXT, date_label TEXT, date_from INTEGER, date_to INTEGER,
       script TEXT, bibliography TEXT)""",
    """CREATE TABLE IF NOT EXISTS corpus_texts (id TEXT PRIMARY KEY, source_id TEXT NOT NULL, name TEXT, object_id TEXT,
       script TEXT, genre TEXT, date_label TEXT, date_from INTEGER, date_to INTEGER, findspot TEXT, object_type TEXT,
       material TEXT, location TEXT, inventory TEXT, bibliography TEXT)""",
    """CREATE TABLE IF NOT EXISTS corpus_sentences (id TEXT PRIMARY KEY, text_id TEXT, source_id TEXT NOT NULL, line TEXT,
       paragraph TEXT, position INTEGER, glyphs_mdc TEXT, transliteration TEXT, translations TEXT, date_from INTEGER, date_to INTEGER)""",
    """CREATE TABLE IF NOT EXISTS corpus_attestations (id TEXT PRIMARY KEY, lemma_id TEXT NOT NULL, sentence_id TEXT NOT NULL,
       token_index INTEGER, form TEXT, glyphs_mdc TEXT, gloss TEXT, source_id TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS corpus_att_lemma ON corpus_attestations(lemma_id)",
]
TABLES = ["corpus_attestations", "corpus_sentences", "corpus_texts", "corpus_objects", "corpus_thesaurus", "corpus_links",
          "corpus_senses", "corpus_forms", "corpus_lemmas"]


def key(text: str) -> str:
    """Search key: NFC, lowercase, Coptic supralinear strokes and combining marks removed."""
    text = unicodedata.normalize("NFD", (text or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c) and c not in "︤︥︦⸗=")
    return unicodedata.normalize("NFC", text)


def ensure_schema(conn=None) -> None:
    own = conn is None
    conn = conn or connect()
    try:
        for statement in SCHEMA:
            conn.execute(statement)
        conn.commit()
    finally:
        if own:
            conn.close()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Batch:
    """Collects rows for one source and writes them in one transaction (re-import replaces the source)."""

    def __init__(self, source: dict[str, Any]):
        self.source = source
        self.rows: dict[str, list[tuple]] = {t: [] for t in TABLES}
        self.seen: dict[str, set] = {t: set() for t in TABLES}

    def add(self, table: str, row: tuple, unique: str | None = None) -> None:
        if unique is not None:
            if unique in self.seen[table]:
                return
            self.seen[table].add(unique)
        self.rows[table].append(row)

    def write(self) -> dict[str, int]:
        sid = self.source["id"]
        with transaction() as conn:
            for statement in SCHEMA:
                conn.execute(statement)
            for table in TABLES:
                conn.execute(f"DELETE FROM {table} WHERE source_id=?", (sid,))
            conn.execute("DELETE FROM corpus_sources WHERE id=?", (sid,))
            conn.execute("INSERT INTO corpus_sources (id,kind,title,citation,license,url,version,imported_at) VALUES (?,?,?,?,?,?,?,?)",
                         (sid, self.source["kind"], self.source["title"], self.source.get("citation"), self.source.get("license"),
                          self.source.get("url"), self.source.get("version"), _now()))
            for table, rows in self.rows.items():
                if rows:
                    marks = ",".join("?" * len(rows[0]))
                    conn.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
        counts = {table: len(rows) for table, rows in self.rows.items() if rows}
        from ..storage import audit
        audit.record("system", "corpus.import", sid, {"title": self.source["title"], "counts": counts})
        return counts


# ------------------------------------------------------------------ TLA
TLA_SOURCE = {"kind": "corpus", "title": "Thesaurus Linguae Aegyptiae", "license": "CC BY-SA 4.0",
              "citation": "Thesaurus Linguae Aegyptiae, Berlin-Brandenburgische Akademie der Wissenschaften / Sächsische Akademie der "
                          "Wissenschaften zu Leipzig (ed. T. S. Richter, D. A. Werning et al.)",
              "url": "https://thesaurus-linguae-aegyptiae.de"}


def _ths_entries(node: Any) -> Iterator[dict[str, Any]]:
    """Every thesaurus reference (eclass BTSThsEntry) anywhere inside a passport."""
    if isinstance(node, dict):
        if node.get("eclass") == "BTSThsEntry" and node.get("name"):
            yield node
        for value in node.values():
            yield from _ths_entries(value)
    elif isinstance(node, list):
        for value in node:
            yield from _ths_entries(value)


def _first(passport: Any, kind: str) -> str | None:
    return next((t["name"] for t in _ths_entries(passport) if t.get("type") == kind), None)


def _all_strings(node: Any, wanted: str) -> list[str]:
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == wanted:
                out += [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str)]
            else:
                out += _all_strings(v, wanted)
    elif isinstance(node, list):
        for v in node:
            out += _all_strings(v, wanted)
    return out


def _tla_docs(paths: Iterable[str]) -> Iterator[dict[str, Any]]:
    for path in paths:
        if path.endswith(".jsonl") or path.endswith(".jsonl.gz"):
            opener = gzip.open if path.endswith(".gz") else open
            with opener(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        yield json.loads(line)
            continue
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
        if "doc" in doc and isinstance(doc["doc"], dict):  # TLA web API envelope
            yield doc["doc"]
            for related in (doc.get("related") or {}).values():
                if isinstance(related, dict):
                    yield from (r for r in related.values() if isinstance(r, dict) and r.get("eclass"))
        else:
            yield doc


def _expand(path: str | os.PathLike) -> list[str]:
    path = os.fspath(path)
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "**", "*.json"), recursive=True)
                      + glob.glob(os.path.join(path, "**", "*.jsonl*"), recursive=True))
    return [path]


def import_tla(path: str, source_id: str = "tla", version: str | None = None) -> dict[str, Any]:
    """Import TLA records from a directory or file (BTS JSON, TLA API JSON, or the flat JSONL release)."""
    batch = Batch({"id": source_id, "version": version, **TLA_SOURCE})
    docs = list(_tla_docs(_expand(path)))
    ths: dict[str, tuple[int | None, int | None]] = {}
    for doc in docs:  # thesaurus first: texts and objects refer to its dates
        if doc.get("eclass") == "BTSThsEntry":
            begin = next(iter(_all_strings(doc.get("passport"), "beginning")), None)
            end = next(iter(_all_strings(doc.get("passport"), "end")), None)
            span = (int(begin), int(end)) if begin and end else chronology.date_range(doc.get("name"))
            ref = next(iter(_all_strings(doc.get("passport"), "reference")), None)
            ths[doc["id"]] = span or (None, None)
            batch.add("corpus_thesaurus", (doc["id"], source_id, doc.get("name"), doc.get("type"),
                                           *(span or (None, None)), ref or (chronology.CITATION if span else None)), doc["id"])
    texts: dict[str, tuple[int | None, int | None]] = {}
    for doc in docs:
        eclass = doc.get("eclass")
        if eclass == "BTSLemmaEntry":
            _tla_lemma(batch, doc, source_id)
        elif eclass in {"BTSText", "BTSTCObject"}:
            span = _tla_span(doc, ths)
            texts[doc["id"]] = span
            _tla_text_or_object(batch, doc, source_id, span)
    for doc in docs:
        if doc.get("eclass") == "BTSSentence":
            _tla_sentence(batch, doc, source_id, texts)
        elif "lemmatization" in doc or ("transcription" in doc and "eclass" not in doc):
            _tla_flat_sentence(batch, doc, source_id)
    counts = batch.write()
    return {"source": source_id, "records_read": len(docs), "imported": counts}


def _tla_span(doc: dict[str, Any], ths: dict[str, tuple]) -> tuple[int | None, int | None]:
    for entry in _ths_entries(doc.get("passport")):
        if entry.get("type") == "date":
            span = ths.get(entry["id"]) or chronology.date_range(entry["name"])
            if span and span[0] is not None:
                return span
    return (None, None)


def _tla_lemma(batch: Batch, doc: dict[str, Any], sid: str) -> None:
    lid = f"tla:{doc['id']}"
    span = doc.get("time_span") or {}
    stage = "demotic" if str(doc["id"]).startswith("d") else "coptic" if str(doc["id"]).startswith("C") else "egyptian"
    words = doc.get("words") or []
    mdc = next((w.get("glyphs", {}).get("mdc") for w in words if w.get("glyphs", {}).get("mdc")), None)
    biblio = "; ".join(_all_strings(doc.get("passport"), "bibliographical_text_field")) or None
    extra = {"external": doc.get("externalReferences"), "attestation_periods": doc.get("attestations")}
    batch.add("corpus_lemmas", (lid, sid, stage, doc.get("name") or "", key(doc.get("name") or ""), mdc, doc.get("type"),
                                doc.get("subtype"), span.get("begin"), span.get("end"), biblio, "attested",
                                json.dumps(extra, ensure_ascii=False)), lid)
    for lang, glosses in (doc.get("translations") or {}).items():
        for gloss in glosses or []:
            batch.add("corpus_senses", (lid, lang, gloss, biblio, sid), f"{lid}|{lang}|{gloss}")
    for word in words:
        form = (word.get("transcription") or {}).get("unicode")
        if form:
            batch.add("corpus_forms", (lid, form, key(form), "hieroglyphic", "spelling", sid), f"{lid}|{form}")
    for relation, targets in (doc.get("relations") or {}).items():
        if relation in {"successor", "predecessor", "root", "partOf", "referencedBy"}:
            for target in targets or []:
                if target.get("eclass") == "BTSLemmaEntry":
                    batch.add("corpus_links", (lid, f"tla:{target['id']}", relation, sid, target.get("name")))


def _tla_text_or_object(batch: Batch, doc: dict[str, Any], sid: str, span: tuple) -> None:
    passport = doc.get("passport")
    date_label = _first(passport, "date")
    bibliography = "; ".join(_all_strings(passport, "bibliographical_text_field")) or None
    inventory = next(iter(_all_strings(passport, "inventory_number")), None)
    common = (_first(passport, "objecttype"), _first(passport, "material"), _first(passport, "location"), inventory)
    if doc["eclass"] == "BTSTCObject":
        batch.add("corpus_objects", (doc["id"], sid, doc.get("name"), *common, _first(passport, "findSpot"), date_label,
                                     span[0], span[1], _first(passport, "script"), bibliography), doc["id"])
        return
    genre = next(iter(_all_strings(passport, "comment_on_texttype")), None) or _first(passport, "texttype")
    object_id = next((p["id"] for path in doc.get("paths") or [] for p in path if p.get("eclass") == "BTSTCObject"), None)
    batch.add("corpus_texts", (doc["id"], sid, doc.get("name"), object_id, _first(passport, "script"), genre, date_label,
                               span[0], span[1], _first(passport, "findSpot"), *common, bibliography), doc["id"])


def _tla_sentence(batch: Batch, doc: dict[str, Any], sid: str, texts: dict[str, tuple]) -> None:
    context = doc.get("context") or {}
    tokens = [t for t in doc.get("tokens") or [] if t.get("type", "word") == "word"]  # skip line/column markers
    translit = (doc.get("transcription") or {}).get("unicode") or " ".join(
        (t.get("transcription") or {}).get("unicode") or t.get("label") or "" for t in tokens).strip()
    glyphs = doc.get("glyphs") if isinstance(doc.get("glyphs"), str) else (doc.get("glyphs") or {}).get("mdc")
    span = texts.get(context.get("textId"), (None, None))
    batch.add("corpus_sentences", (doc["id"], context.get("textId"), sid, context.get("line"), context.get("paragraph"),
                                   context.get("pos"), glyphs, translit, json.dumps(doc.get("translations") or {}, ensure_ascii=False),
                                   span[0], span[1]), doc["id"])
    if context.get("textId") and context["textId"] not in texts:
        name = next((p.get("name") for p in (doc.get("relations") or {}).get("partOf", []) if p.get("id") == context["textId"]), None)
        batch.add("corpus_texts", (context["textId"], sid, name, None, None, None, None, None, None, None, None, None, None, None, None),
                  context["textId"])
    for index, token in enumerate(tokens):
        lemma_id = (token.get("lemma") or {}).get("id")
        if not lemma_id:
            continue
        form = (token.get("transcription") or {}).get("unicode") or token.get("label")
        batch.add("corpus_attestations", (token.get("id") or f"{doc['id']}:{index}", f"tla:{lemma_id}", doc["id"], index, form,
                                          (token.get("glyphs") or {}).get("mdc"), (token.get("flexion") or {}).get("lingGloss"), sid))
        stub = f"tla:{lemma_id}"
        pos = ((token.get("lemma") or {}).get("POS") or {})
        batch.add("corpus_lemmas", (stub, sid, "egyptian", token.get("label") or form or "", key(token.get("label") or form or ""),
                                    None, pos.get("type"), pos.get("subtype"), None, None, None, "attested",
                                    json.dumps({"stub": True}),), stub)
        for lang, glosses in (token.get("translations") or {}).items():
            for gloss in glosses or []:
                batch.add("corpus_senses", (stub, lang, gloss, "TLA token gloss", sid), f"{stub}|{lang}|{gloss}")


def _tla_flat_sentence(batch: Batch, row: dict[str, Any], sid: str) -> None:
    """TLA JSONL release: lemmatization 'ID|label ID|label …', glossing, translation, dateNotBefore/After."""
    sentence_id = str(row.get("id") or row.get("sentence_id") or f"row{len(batch.rows['corpus_sentences'])}")
    translit = row.get("transcription") or row.get("transliteration") or ""
    date_from = row.get("dateNotBefore")
    date_to = row.get("dateNotAfter")
    date_from = int(date_from) if str(date_from or "").lstrip("-").isdigit() else None
    date_to = int(date_to) if str(date_to or "").lstrip("-").isdigit() else None
    translation = row.get("translation")
    batch.add("corpus_sentences", (sentence_id, row.get("text_id"), sid, row.get("line"), None, None, row.get("hieroglyphs"),
                                   translit, json.dumps({"de": [translation]} if isinstance(translation, str) else translation or {},
                                                        ensure_ascii=False), date_from, date_to), sentence_id)
    glosses = (row.get("glossing") or "").split()
    for index, item in enumerate((row.get("lemmatization") or "").split()):
        lemma_id, _, label = item.partition("|")
        if not lemma_id:
            continue
        lid = f"tla:{lemma_id}"
        batch.add("corpus_lemmas", (lid, sid, "egyptian", label, key(label), None, None, None, None, None, None, "attested",
                                    json.dumps({"stub": True})), lid)
        batch.add("corpus_attestations", (f"{sentence_id}:{index}", lid, sentence_id, index, label, None,
                                          glosses[index] if index < len(glosses) else None, sid))


# ------------------------------------------------------------------ Coptic
def import_coptic(path: str | None = None) -> dict[str, Any]:
    path = path or str(DATA / "coptic" / "ccl.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    sid = "ccl"
    batch = Batch({"id": sid, "kind": "dictionary", "title": data["source"], "citation": data["citation"], "license": data["license"],
                   "url": f"https://doi.org/{data['doi']}", "version": "1.2"})
    for entry in data["entries"]:
        lid = f"ccl:{entry['id']}"
        lemma_form = next((f for f in entry["forms"] if f["type"] == "lemma"), entry["forms"][0])
        biblio = "; ".join(dict.fromkeys(s["bibl"] for s in entry["senses"] if s.get("bibl"))) or None
        extra = {"tla_id": entry["id"], "gender": entry["gender"], "entry_type": entry["type"], "etymology": entry["etym"]}
        batch.add("corpus_lemmas", (lid, sid, "coptic", lemma_form["orth"], key(lemma_form["orth"]), None, entry["pos"], entry["type"],
                                    250, 1300, biblio, "attested", json.dumps(extra, ensure_ascii=False)), lid)
        for form in entry["forms"]:
            batch.add("corpus_forms", (lid, form["orth"], key(form["orth"]), ",".join(form["dialects"]), form["type"], sid),
                      f"{lid}|{form['orth']}|{','.join(form['dialects'])}")
        for sense in entry["senses"]:
            for lang in ("en", "de", "fr"):
                if sense.get(lang):
                    batch.add("corpus_senses", (lid, lang, sense[lang], sense.get("bibl"), sid))
        for tla in entry["etym"].get("egyptian_tla", []):
            batch.add("corpus_links", (lid, f"tla:{tla}", "descends_from", sid, "CCL etymology (TLA Egyptian lemma)"))
        for tla in entry["etym"].get("demotic_tla", []):
            batch.add("corpus_links", (lid, f"tla:{tla}", "descends_from_demotic", sid, "CCL etymology (TLA Demotic lemma)"))
    return {"source": sid, "imported": batch.write()}


# ------------------------------------------------------------------ teaching lexicon
def import_teaching() -> dict[str, Any]:
    sid = "teaching"
    batch = Batch({"id": sid, "kind": "teaching", "title": "Trans-Late Ancient Relics teaching lexicon",
                   "citation": "Learner lexicon of the app; glosses are reviewed for teaching but not yet linked to attestations.",
                   "license": "project license"})
    for path in sorted((DATA / "lexicon").glob("*.json")):
        for entry in json.loads(path.read_text(encoding="utf-8")):
            translit = entry.get("transliteration") or ""
            lid = f"teaching:{translit}"
            batch.add("corpus_lemmas", (lid, sid, "middle_egyptian", translit, key(translit), entry.get("mdc"), entry.get("pos"), None,
                                        -2000, -1300, None, "teaching", json.dumps({"notes": entry.get("notes"),
                                                                                    "confidence": entry.get("confidence")}, ensure_ascii=False)), lid)
            for lang, field in (("en", "english"), ("sw", "swahili")):
                for gloss in entry.get(field) or []:
                    batch.add("corpus_senses", (lid, lang, gloss, "app teaching lexicon", sid))
    return {"source": sid, "imported": batch.write()}


def ensure_bundled() -> dict[str, Any]:
    """Load the bundled sources once (Coptic lexicon, TLA sample records, teaching lexicon)."""
    ensure_schema()
    conn = connect()
    try:
        present = {r[0] for r in conn.execute("SELECT id FROM corpus_sources").fetchall()}
    finally:
        conn.close()
    done = {}
    if "ccl" not in present:
        done["ccl"] = import_coptic()
    if "tla-samples" not in present:
        done["tla-samples"] = import_tla(str(DATA / "corpus" / "tla_samples"), "tla-samples", "TLA software test samples")
    if "teaching" not in present:
        done["teaching"] = import_teaching()
    return done


# ------------------------------------------------------------------ queries
def _rows(sql: str, args: tuple = ()) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def stats() -> dict[str, Any]:
    ensure_bundled()
    out = {"sources": _rows("SELECT id,kind,title,license,version,imported_at FROM corpus_sources ORDER BY id")}
    for table in ("corpus_lemmas", "corpus_senses", "corpus_forms", "corpus_attestations", "corpus_sentences", "corpus_texts", "corpus_objects"):
        out[table.replace("corpus_", "")] = _rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
    out["by_stage"] = {r["stage"]: r["n"] for r in _rows("SELECT stage, COUNT(*) AS n FROM corpus_lemmas GROUP BY stage")}
    out["by_status"] = {r["status"]: r["n"] for r in _rows("SELECT status, COUNT(*) AS n FROM corpus_lemmas GROUP BY status")}
    return out


def search(query: str, stage: str | None = None, lang: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
    """Find lemmas by spelling (any form) or by gloss."""
    ensure_bundled()
    q = key(query)
    if not q:
        return []
    limit = max(1, min(int(limit), 100))
    stage_sql, args = ("AND l.stage=?", (stage,)) if stage else ("", ())
    by_form = _rows(f"""SELECT DISTINCT l.id FROM corpus_lemmas l LEFT JOIN corpus_forms f ON f.lemma_id=l.id
                       WHERE (l.lemma_key=? OR f.form_key=?) {stage_sql} LIMIT ?""", (q, q, *args, limit))
    lang_sql = "AND s.lang=?" if lang else ""
    by_gloss = _rows(f"""SELECT DISTINCT l.id FROM corpus_senses s JOIN corpus_lemmas l ON l.id=s.lemma_id
                        WHERE LOWER(s.gloss) LIKE ? {lang_sql} {stage_sql} LIMIT ?""",
                     (f"%{q}%", *((lang,) if lang else ()), *args, limit))
    ids = list(dict.fromkeys([r["id"] for r in by_form] + [r["id"] for r in by_gloss]))[:limit]
    return [summary(i) for i in ids]


def summary(lemma_id: str) -> dict[str, Any]:
    row = _rows("SELECT * FROM corpus_lemmas WHERE id=?", (lemma_id,))
    if not row:
        return {}
    lemma = row[0]
    senses = _rows("SELECT lang, gloss FROM corpus_senses WHERE lemma_id=?", (lemma_id,))
    return {"id": lemma["id"], "lemma": lemma["lemma"], "stage": lemma["stage"], "pos": lemma["pos"], "status": lemma["status"],
            "source": lemma["source_id"], "glosses": {s["lang"]: [x["gloss"] for x in senses if x["lang"] == s["lang"]] for s in senses},
            "dates": chronology.describe(lemma["date_from"], lemma["date_to"])}


def lemma(lemma_id: str) -> dict[str, Any] | None:
    """A lemma with its senses, forms, links and every attestation with full provenance."""
    ensure_bundled()
    found = _rows("SELECT * FROM corpus_lemmas WHERE id=?", (lemma_id,))
    if not found:
        return None
    record = found[0]
    record["extra"] = json.loads(record["extra"]) if record.get("extra") else {}
    record["dates"] = chronology.describe(record["date_from"], record["date_to"])
    record["senses"] = _rows("SELECT lang, gloss, citation, source_id FROM corpus_senses WHERE lemma_id=?", (lemma_id,))
    record["forms"] = _rows("SELECT form, variety, kind FROM corpus_forms WHERE lemma_id=?", (lemma_id,))
    record["links"] = (_rows("SELECT to_id AS id, relation, note FROM corpus_links WHERE from_id=?", (lemma_id,))
                       + _rows("SELECT from_id AS id, 'inverse:' || relation AS relation, note FROM corpus_links WHERE to_id=?", (lemma_id,)))
    record["attestations"] = attestations(lemma_id)
    record["source"] = _rows("SELECT * FROM corpus_sources WHERE id=?", (record["source_id"],))[0]
    return record


def attestations(lemma_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = _rows("""SELECT a.form, a.glyphs_mdc, a.gloss, a.token_index, s.id AS sentence_id, s.transliteration AS sentence,
                    s.translations, s.line, s.paragraph, s.glyphs_mdc AS sentence_glyphs, t.id AS text_id, t.name AS text, t.genre,
                    t.script, t.findspot, t.object_type, t.material, t.location, t.inventory, t.bibliography,
                    COALESCE(t.date_label, '') AS date_label, COALESCE(s.date_from, t.date_from) AS date_from,
                    COALESCE(s.date_to, t.date_to) AS date_to, a.source_id
                    FROM corpus_attestations a JOIN corpus_sentences s ON s.id=a.sentence_id
                    LEFT JOIN corpus_texts t ON t.id=s.text_id WHERE a.lemma_id=? LIMIT ?""", (lemma_id, limit))
    from ..periods import explain_gloss
    for row in rows:
        row["translations"] = json.loads(row["translations"]) if row.get("translations") else {}
        if row.get("gloss"):
            row["grammar"] = explain_gloss(row["gloss"])["reading"]
        row["dates"] = chronology.describe(row.pop("date_from"), row.pop("date_to"))
    return rows
