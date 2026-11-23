# Ancient Language Ladder

Any-to-any translation between English, Swahili and the oldest recoverable stage of each language below. Every language reads and writes through one shared, language-neutral meaning frame, so each pair works in both directions: English ⇄ Ge'ez, Swahili ⇄ Sumerian, Old Latin ⇄ Old Amharic, hieroglyphs ⇄ Arabic, and so on.

## Languages

| Id | Language | Oldest stage used | Status | Native scripts produced |
|---|---|---|---|---|
| `archaic_hieroglyphic` | Archaic / proto-hieroglyphic Egyptian | Abydos tomb U-j labels, Naqada III, c. 3250 BCE | attested words; **no sentences** | hieroglyphs |
| `archaic_sumerian` | Archaic Sumerian | Abu Salabikh / Fara tablets, c. 2600-2500 BCE | attested words, composed sentences | cuneiform |
| `old_egyptian` | Old Egyptian | Old Kingdom, c. 2686-2160 BCE (keeps *z* ≠ *s*) | attested words, composed sentences | hieroglyphs |
| `middle_egyptian` | Middle Egyptian | c. 2055-1650 BCE (applies *z* > *s*) | attested words, composed sentences | hieroglyphs |
| `old_latin` | Old Latin | c. 600-150 BCE (Lapis Niger, Duenos vase) | attested words, composed sentences | archaic capitals, Old Italic letters |
| `old_arabic` | Old Arabic (pre-Islamic) | Safaitic, Nabataeo-Arabic, Namara 328 CE | attested words, composed sentences | Safaitic, early undotted Arabic (rasm), Arabic |
| `geez` | Ge'ez | Aksumite inscriptions, c. 4th century CE | attested words, composed sentences | fidel |
| `old_amharic` | Old Amharic | 14th-century royal songs | attested words, composed sentences | fidel |
| `proto_semitic` | Proto-Semitic | reconstructed, c. 4000 BCE or earlier | **reconstructed** (`*` forms) | none (never written) |
| `proto_world` | Proto-World | hypothetical (Bengtson & Ruhlen 1994) | **hypothetical**; roots only, no grammar | none |
| `english`, `swahili` | Modern pivots | — | — | Latin alphabet |

## How it works

```text
any input text ──► parser ──► meaning frame ──► realizer ──► text + native scripts + provenance
                                   ▲
   English / Swahili: rule parsers │  ancient languages: index of every form
                                   │  the realizer can write (transliteration,
                                   │  diacritic-free spelling and native script)
```

| Module | Role |
|---|---|
| `app/data/ancient/lexicon.json` | Concept lexicon: 33 nouns, 2 adjectives and 16 verbs aligned across all languages, each with a confidence and notes |
| `app/ancient/grammar.py` | One realizer per language: case, agreement, word order, verb conjugation for 8 persons × past/present |
| `app/ancient/parsing.py` | English and Swahili parsers; reverse index for every ancient language and script |
| `app/ancient/scripts.py` | Cuneiform, hieroglyph, fidel, Old Italic, Safaitic and Arabic renderers; every glyph comes from its official Unicode name |
| `app/ancient/engine.py` | Language registry, aliases, `translate()` and `concept_table()` |

Grammar each realizer applies:

- **Sumerian**: SOV, ergative *-e* on transitive subjects, terminative *-še3*, *mu-/ba-* prefixes, *ḫamṭu* (perfective) and *marû* (imperfective) suffix sets, enclitic copula (*lugal-me-en* "I am king").
- **Egyptian**: VSO, *sḏm.n.f* perfect and *sḏm.f* present, suffix pronouns, independent pronouns (*jnk nswt*), feminine adjective agreement, *mḥ jb* "fill the heart" for *trust*.
- **Old Latin**: archaic endings (*-os*, *-om*, dative *-ei/-oi/-ai*, perfect *-ei*), verbs governing dative/accusative/*ad*/*in*, SOV.
- **Old Arabic**: VSO, case endings and nunation, definite article with sun-letter assimilation, perfect and imperfect conjugation, prepositions *ʿalā*, *bi-*, *ʾilā*.
- **Ge'ez**: VSO, *-ku* perfect, accusative *-a*, *ba-* clitic.
- **Old Amharic**: SOV, definite *-u/-wa*, accusative *-n*, copula *nəññ/näw*.
- **Proto-Semitic**: reconstructed case vowels and suffix conjugation (*-ku*), prefixed imperfect.

## Honesty rules

Every result carries a `status` and a `confidence`:

| Status | Meaning |
|---|---|
| `attested` | A single word found in the language's own texts (spelling may be normalized). |
| `composed` | A sentence built by grammar rules from attested words. It is **not** a quotation of an ancient text. Confidence is capped at 0.75. |
| `reconstructed` / `reconstructed_composition` | Proto-Semitic forms; capped at 0.5. |
| `hypothetical` | Proto-World roots; capped at 0.15. |
| `not_attested_for_this_structure` | The language did not write this kind of sentence (archaic hieroglyphs, Proto-World). Only content-word labels are given, with a `refusal` explanation. |

Gaps are reported, never filled: a concept with no known form in a language comes back as a `gap`. Unknown input words are listed in `parse.unknown_words`, and homographs (Latin *estis*, Sumerian 𒀭 *an/diĝir*, vowel-less Safaitic) are listed in `parse.ambiguities`.

## Using it

API:

```http
GET  /api/ancient/languages
POST /api/ancient/translate      {"text": "The truth, I have put my trust in", "source": "english", "targets": []}
GET  /api/ancient/concepts/truth
```

`targets` may name any language ids or aliases (`sw`, `latin`, `ge'ez`, `proto-semitic`, ...); empty means all.

CLI:

```bash
python cli.py ladder "The king made a great house" --brief
python cli.py ladder "ተወከልኩ፡በአማን።" --source geez --target english --target swahili --brief
```

Browser: the **Ancient Ladder** tab. Paste native script or type transliteration (diacritics and sign numbers optional), pick a source and target, and use *Translate from here* on any result to continue from that language.

Example: *"The truth, I have put my trust in"*

| Language | Output |
|---|---|
| Swahili | Niliamini ukweli |
| Archaic Sumerian | niĝ-gi-na-še3 šag4 mu-ĝal2 · 𒃻𒄀𒈾𒂠 𒊮 𒈬𒅅 |
| Old Egyptian | mḥ.n.j jb.j m mꜣꜥt · 𓎔𓈖𓀀 𓄣𓏤𓀀 𓅓 𓐙𓂝𓏏𓆄 |
| Old Latin | ueritatei credidei · 𐌖𐌄𐌓𐌉𐌕𐌀𐌕𐌄𐌉·𐌂𐌓𐌄𐌃𐌉𐌃𐌄𐌉 |
| Old Arabic | tawakkaltu ʿalā l-ḥaqqi · 𐪉𐪅𐪋𐪁𐪉 𐪒𐪁 𐪀𐪂𐪄 · ٮوكلٮ على الحٯ |
| Ge'ez | tawakkalku ba-ʾamān · ተወከልኩ፡በአማን። |
| Old Amharic | bä-ʾəwnät ʾammänku · በእውነት፡አመንኩ። |
| Proto-Semitic | \*ʔaminku \*bi-ʔamāni |
| Proto-World | no sentence (no grammar exists) |
| Archaic hieroglyphic | label only: mꜣꜥt 𓐙𓂝𓏏𓆄 |

## Limits and next steps

- The vocabulary is a curated core, not a full dictionary. Add a concept by adding one entry to `lexicon.json`; the parsers pick it up automatically, and `tests/test_ancient_ladder.py` checks that every new form reads back.
- Sentences cover statements (subject, verb, object, one adjective) and "I am …" sentences. Questions, negation, relative clauses and future tense are not modelled yet.
- Earliest Sumerian and Old Amharic left much grammar unwritten; the fuller later spellings are used and noted per result.
- Display of native scripts depends on installed fonts (Noto Sans Cuneiform, Egyptian Hieroglyphs, Ethiopic, Old Italic and Old North Arabian cover all of them).
