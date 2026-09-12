# Trans-Late Ancient Relics — ESHB Ancient Egyptian Tutor

This repository is a working educational system that keeps **two different jobs** separate:

1. **ESHB** — a modern, reversible English/Swahili/IPA ↔ hieroglyphic bridge.
2. **Middle Egyptian** — historical language learning: lexicon, grammar, transliteration, hieroglyphic signs, determinatives/phonetic-complement concepts, lessons and guarded translation.

## Why the distinction matters

Ancient Egyptian hieroglyphic spelling is not an A–Z substitution cipher. It commonly records consonants, uses one-, two- and three-consonant signs, logograms/ideograms, phonetic complements and semantic determinatives. Vowels are normally omitted in hieroglyphic/hieratic Egyptian, so exact Middle Kingdom pronunciation is only partially reconstructable.

ESHB is intentionally modern. Its **strict form** places a separator between logical tokens so conversion is algorithmically reversible. Its display form is decorative/readable but is not guaranteed to be uniquely decodable without the strict token boundaries.

## Features

- English → strict/display ESHB
- Swahili → strict/display ESHB, including CH, SH, DH, TH, KH, GH, NY, NG and NG'
- Strict ESHB → normalized orthographic spelling
- IPA → ESHB and ESHB → IPA for common English/Swahili IPA symbols, with reversible Unicode fallback
- Middle Egyptian uniliteral sign table
- Manuel de Codage ↔ Unicode Egyptological transliteration conversion for the core special consonants
- Egyptological transliteration → hieroglyph rendering
  - selected lexicon-canonical/logographic forms when present
  - explicitly labeled uniliteral fallback otherwise
- Uniliteral hieroglyph parser → transliteration
- Trilingual learner dictionary: Egyptian transliteration + English + Swahili
- 26 original course lessons from script basics through verbal constructions and inscription analysis
- Guarded dictionary/grammar translator that returns confidence, ambiguity and unsupported tokens instead of inventing a fake historical translation
- Vocabulary quiz generator
- SQLite learner progress API
- FastAPI backend + responsive browser UI + CLI + tests

## Run

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Interactive API docs:

```text
http://127.0.0.1:8000/docs
```

## CLI

```bash
python cli.py encode "Habari yako" --lang swahili
python cli.py decode "𓉔·𓄿·𓃀·𓄿·𓂋·𓇋"
python cli.py ipa-encode "hɑbari"
python cli.py hiero "nfr pr"
python cli.py dict "nzuri" --lang swahili
python cli.py translate "I am a scribe" --source english
```

## Translation pipeline

The intended historical pipeline is:

```text
English/Swahili meaning
    ↓
semantic/lexical analysis
    ↓
Middle Egyptian vocabulary
    ↓
Middle Egyptian morphology + grammar
    ↓
Egyptological transliteration
    ↓
attested/canonical hieroglyphic spelling
    ↓
phonetic complements + determinatives
    ↓
sign-group/layout rendering
```

Historical reverse analysis is:

```text
inscription direction + sign segmentation
    ↓
Gardiner/sign identification
    ↓
phonograms / logograms / determinatives
    ↓
transliteration
    ↓
word segmentation + morphology
    ↓
syntax
    ↓
lexical sense disambiguation
    ↓
English/Swahili translation
```

The current historical translator deliberately supports curated dictionary entries and a set of teaching grammar templates. It **does not claim unrestricted machine translation of arbitrary inscriptions**. Free-form Ancient Egyptian translation requires a substantially larger attested corpus, morphological analyzer, period-aware grammar, sign-group resolver and human-verifiable lexical database.

## Dictionary design

Every lexicon item can contain:

```json
{
  "transliteration": "nfr",
  "english": ["good", "beautiful", "perfect"],
  "swahili": ["nzuri", "mrembo", "kamili"],
  "pos": "adjective",
  "hieroglyphs": "𓄤",
  "gardiner": ["F35"],
  "mdc": "F35",
  "notes": "...",
  "confidence": "high"
}
```

This project ships a curated **teaching core lexicon**, not a replacement for a professional Egyptological dictionary. Expand `app/data/lexicon/*.json` with source-linked entries rather than scraping copyrighted dictionaries.

## Accuracy policy

The system distinguishes:
- **reversible bridge encoding** from
- **historical transliteration**, from
- **lexical glossing**, from
- **grammatical translation**, from
- **historical pronunciation reconstruction**.

When a historical spelling is not stored, the renderer returns `authenticity = phonetic_fallback`. That is deliberate: an uniliteral spelling can represent consonants but should not be mislabeled as an attested ancient spelling.

## Sources used to design the linguistic model

The in-app References tab lists authoritative/reference material, including UCL Digital Egypt on the hieroglyphic writing system and sound signs, UCL material on pronunciation uncertainty, and bibliographic pointers to modern Middle Egyptian grammar/reference works.

No copyrighted dictionary or textbook chapter is reproduced by this project. Lesson wording and the trilingual teaching entries are original educational content.

## Next research-grade extensions

For a production Egyptological translator, add:
- an attestation database keyed by lemma, period, genre and source;
- a complete Gardiner/Unicode/MdC sign database;
- biliteral/triliteral and phonetic-complement parser;
- determinative classifier;
- Middle Egyptian morphological analyzer and generator;
- VSO/nominal/adjectival/adverbial/relative-clause parser;
- named-entity and royal-title handling;
- sign-block layout engine using Egyptian Hieroglyph Format Controls / MdC rendering;
- aligned Egyptian ↔ English/Swahili corpus with sentence-level provenance;
- Coptic evidence layer and reconstruction confidence for pronunciation;
- editor/reviewer workflow so every proposed lexical or grammatical addition is auditable.

## License

Code: MIT-style use is permitted for this generated project. Historical signs and Unicode characters are not proprietary to this codebase. Verify licensing separately for any external corpora you later import.


## Repository implementation

This repository is the canonical implementation for **Trans-Late-Ancient-Relics-**. It includes the FastAPI service, browser UI, command-line tools, curated trilingual teaching data, tests, Docker packaging and GitHub Actions CI.

### Fast verification

```bash
make check
```

### Docker

```bash
docker compose up --build
```

Then open `http://127.0.0.1:8000`.


## Runtime persistence

Learner progress is stored in `data-runtime/tutor_progress.sqlite3` by default. Override the runtime directory with `ESHB_RUNTIME_DIR` or the exact database path with `ESHB_DB_PATH`. Docker Compose mounts this directory as a persistent named volume.
