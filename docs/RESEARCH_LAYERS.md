# Research layers

These ten layers turn the v3 "integration points" into working, tested code. Each section says what is built, where the data comes from, how to use it, and what it still cannot do. Nothing here is presented as more certain than its source.

| # | Layer | Code | Bundled data | Status |
|---|---|---|---|---|
| 1 | Attestation database | `app/corpus/` | 22 TLA sample records, Comprehensive Coptic Lexicon, teaching lexicon | Built; full TLA corpus is imported by the operator |
| 2 | Sign catalog | `app/signs.py`, `scripts/build_sign_catalog.py` | Unicode Unikemet 18.0 (5,067 signs) | Built |
| 3 | Quadrat parser and renderer | `app/quadrat.py` | Noto glyph metrics (1,076 signs) | Built |
| 4 | Period grammar | `app/periods.py` | Feature table with grammar references | Built (diagnostic, not a full parser) |
| 5 | Vision benchmark | `app/vision_bench.py`, `scripts/train_vision.py` | Dataset licence registry, test fixture | Harness built; weights need a GPU and the datasets |
| 6 | Restoration | `app/restoration.py` | Trained on bundled texts at startup | Built; evaluated in-sample only |
| 7 | Vocalization | `app/coptic.py`, `app/data/coptic/etymologies.json` | 44 Egyptian→Coptic etymologies, Coptic phonology | Built |
| 8 | Hieratic, Demotic, Coptic | `app/script_stages.py`, `app/coptic.py`, `app/avatar_chat/reading.py` | Coptic lexicon (11,283 entries) | Coptic full; hieratic/Demotic via transcription |
| 9 | EN/SW evaluation | `app/translation_eval.py` | 4-artifact benchmark, CI baseline | Built; references are drafts until reviewed |
| 10 | Institutional storage | `app/storage/` | — | Built; tested on SQLite and PostgreSQL 16 |

The **Research** tab in the web app exercises 1–4, 6 and 7. Every API route is listed at the end.

## 1. Attestation database

Tables: `corpus_sources`, `corpus_lemmas`, `corpus_forms`, `corpus_senses`, `corpus_links`, `corpus_thesaurus`, `corpus_objects`, `corpus_texts`, `corpus_sentences`, `corpus_attestations`. An attestation ties a lemma to a sentence, and through it to the text, the object (museum number, find place), the line and the date range. Dates come from the TLA thesaurus where it has them, otherwise from the Hornung–Krauss–Warburton chronology (`app/corpus/chronology.py`).

Importers:

- **TLA BTS JSON** (lemma, sentence, text, object and thesaurus records, including the TLA web API envelope `{doc, related}`).
- **TLA flat JSONL** (the Hugging Face sentence release: `transcription`, `lemmatization` "ID|label", `glossing`, `translation`, `dateNotBefore/After`).
- **Comprehensive Coptic Lexicon** v1.2 TEI (built into `app/data/coptic/ccl.json.gz` by `scripts/build_coptic_lexicon.py`).
- The platform's own teaching lexicon, marked `status = teaching` so it is never mistaken for an attestation.

Re-importing a source replaces it in one transaction, and each import is written to the audit log.

```bash
python cli.py corpus import-tla /data/tla --source-id tla-2024
python cli.py corpus stats
python cli.py corpus search ḥtp
```

Limit: the full TLA corpus (≈ 90,000 sentences) is not in the repository. Download it from the TLA or Hugging Face (CC BY-SA 4.0) and import it.

## 2. Sign catalog

`app/data/signs/unikemet.json.gz` is generated from the Unicode Character Database's `Unikemet.txt` (Unicode License v3). Each sign has its glyph, code point, Gardiner/JSesh code, Unikemet catalog code, Hieroglyphica and IFAO numbers, description, functions (logogram, phonogram, determinative…), phonetic values normalized to TLA transliteration (ꞽ → j, ḳ → q), whether it may be mirrored or rotated, and alternative sequences. Variants are signs that share a Gardiner base (A1, A1A…) or are listed as an alternative sequence.

The epigraphy analyzer uses the reviewed core table first and falls back to the catalog, and reports which source each sign came from.

## 3. Quadrats

`app/quadrat.py` parses both encodings into one tree:

- **Unicode** format controls U+13430–13455: vertical and horizontal joiners, segment begin/end, the four corner and middle insertions, overlay, enclosures (cartouche, serekh, ḥwt), mirroring, lost and damaged regions.
- **Manuel de Codage**: `-` `:` `*` `&` `( )` `< >` `//` `#b…#e` `\`, with codes resolved through the catalog.

It converts in both directions and lays out each group using the real glyph boxes of Noto Sans Egyptian Hieroglyphs, then draws SVG (left-to-right or right-to-left, hatched lacunae, cartouche rings). Signs from Extended-A have no font glyph yet; they are listed in `signs_without_font_glyph`.

## 4. Period grammar

`app/periods.py` holds features that date a text: sḏm.n=f, contingent tenses, the three generations of independent pronouns, z/s merger, the definite article, the First Present, Late Egyptian negation bn and perfect jr=f sḏm, the 3pl suffix =sn/=w, and the stative. Each feature names the stages it belongs to and a reference (Gardiner, Allen, Edel, Junge, Layton). `detect()` reports the stages a passage is consistent with and flags anachronisms against a claimed period; `explain_gloss()` reads TLA glossing (`V\tam.act-ngem:stpr.3sg.m`).

It is a diagnostic, not a parser: it finds the features that are written, and says nothing about a passage without them.

## 5. Vision benchmark

`app/vision_bench.py`:

- a licence registry: MMM, MEH and MuMMy (CC BY-SA 4.0) are eligible; the Franken–van Gemert Unas set states no licence and is excluded;
- artifact-level splits, so no monument appears in two splits, with a leakage check;
- top-1/top-5, macro recall and F1, expected calibration error, unknown-sign rejection AUROC and confusion pairs;
- ONNX evaluation.

`scripts/train_vision.py` fine-tunes a backbone (no horizontal flips: mirrored signs change reading direction), calibrates it by temperature scaling, evaluates it on the untouched test split, exports ONNX with a model card and registers it as a candidate.

No weights ship with this repository: training needs the datasets and a GPU. The registry refuses to approve a model below top-1 0.80 or above ECE 0.10, or one trained on a dataset without a licence.

## 6. Restoration

`app/restoration.py` reads Leiden notation (`[...]` lost, `[2]` two words, `n[...]` partly preserved, `[nfr]` editor's restoration, `⸢ ⸣` damaged) and returns, for each gap, a probability distribution over restorations. It also returns the probability of "something else" (including words the model has never seen) and the entropy. The model is an interpolated trigram with Witten–Bell smoothing, trained on the formulae, lesson sentences and imported corpus sentences. Multi-word gaps use beam search.

`python cli.py evaluate restoration` gives leave-one-out top-1, top-5 and ECE. These are in-sample figures; a held-out benchmark needs the full TLA corpus.

## 7. Vocalization

Coptic is the only stage written with vowels. `app/data/coptic/etymologies.json` links 44 Egyptian words to their Coptic descendants (Černý CED; Vycichl DELC), each resolved to a Comprehensive Coptic Lexicon entry with its references. `app/coptic.py` pronounces Sahidic after Layton's grammar: ⲟⲩ as u/w, a doubled vowel as a glottal stop, the unwritten ə in final clusters and before syllabic sonorants, and stress on the full vowel. Everything is labelled as a reconstruction. One pair (ꜥꜣ "great") has no unambiguous lexicon entry and is reported as unresolved.

## 8. Hieratic, Demotic and Coptic

`app/script_stages.py` describes each script stage: dates, direction, Unicode status and how the platform handles it. Coptic is read directly (lexicon, prefixes, pronunciation). Hieratic is handled through hieroglyphic transcription, as Egyptologists do. Demotic is handled through CDD transliteration, with only 12 lexicon links so far. The reading tutor recognizes all three.

## 9. English and Swahili evaluation

`app/translation_eval.py` scores whole artifacts, not lines, so one long papyrus cannot hide failures on many short inscriptions. Metrics are chrF and chrF++ (Popović), exact match and coverage, reported per language. The benchmark contains TLA oBrussels E 3209, two lines of Papyrus Ebers, an offering-formula composite and a lesson composite. References are `tla-draft` or `teaching` until a specialist reviews them; the report counts expert-reviewed artifacts separately. `app/data/eval/baseline.json` is the CI floor: a change that lowers chrF or coverage fails the tests.

## 10. Institutional storage

| Part | Module | Notes |
|---|---|---|
| PostgreSQL | `app/storage/pg.py` | Set `ESHB_DATABASE_URL=postgresql://…`; the same SQL runs on SQLite and PostgreSQL (psycopg 3) |
| Migrations | `app/storage/migrations.py` | Versioned, applied at startup and by `python cli.py migrate` |
| Object store | `app/storage/objects.py` | Content-addressed (SHA-256), local folder or S3-compatible, checksum verified on read |
| Audit log | `app/storage/audit.py` | Hash chain; `verify()` finds the first altered entry. Logs logins, role changes, imports and model changes |
| Model registry | `app/storage/registry.py` | candidate → approved → deployed → retired, with metric and licence gates; one deployed version per name |

Several app servers can share one PostgreSQL database and one S3 bucket. Install `requirements-postgres.txt` for psycopg and boto3. CI runs the whole test suite against PostgreSQL 16.

## API

```text
GET  /api/signs/catalog
GET  /api/signs/lookup?q=
GET  /api/quadrat?text=&direction=ltr|rtl&size=
GET  /api/corpus/stats
GET  /api/corpus/search?q=&stage=&lang=
GET  /api/corpus/lemmas/{id}
GET  /api/coptic/read?text=
GET  /api/coptic/vocalization?egyptian=
GET  /api/scripts/stages
GET  /api/grammar/periods?text=&period=
GET  /api/grammar/gloss?gloss=
GET  /api/restoration?text=
GET  /api/evaluation/translation
GET  /api/vision/datasets
GET  /api/admin/storage            (admin)
GET  /api/admin/audit              (admin)
GET  /api/admin/models             (reviewer)
POST /api/admin/models/{id}/status (admin)
```

## Sources and licences

- Unicode Unikemet, UCD 18.0 — Unicode License v3.
- Thesaurus Linguae Aegyptiae sample records — CC BY-SA 4.0.
- Comprehensive Coptic Lexicon v1.2, doi:10.17169/refubium-2333 — CC BY-SA 4.0.
- Noto Sans Egyptian Hieroglyphs metrics — SIL OFL 1.1.
- E. Hornung, R. Krauss, D. Warburton (eds.), *Ancient Egyptian Chronology*, Leiden 2006.
- B. Layton, *A Coptic Grammar*, 3rd ed., 2011; J. Černý, *Coptic Etymological Dictionary*, 1976; W. Vycichl, *Dictionnaire étymologique de la langue copte*, 1983.
- A. Gardiner, *Egyptian Grammar*, 3rd ed.; J. Allen, *Middle Egyptian*, 3rd ed.; E. Edel, *Altägyptische Grammatik*; F. Junge, *Late Egyptian Grammar*, 2005.
- M. Popović, chrF (WMT 2015) and chrF++ (WMT 2017).
