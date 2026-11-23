# Ancient Language Ladder

Any-to-any translation between English, Swahili and the oldest recoverable stage of each language below. Every language reads and writes through one shared, language-neutral meaning frame, so each pair works in both directions: English ⇄ Ge'ez, Swahili ⇄ Sumerian, Old Latin ⇄ Old Amharic, hieroglyphs ⇄ Arabic, and so on.

## Languages

| Id | Language | Oldest stage used | Status | Native scripts produced |
|---|---|---|---|---|
| `archaic_hieroglyphic` | Archaic / proto-hieroglyphic Egyptian | Abydos tomb U-j labels, Naqada III, c. 3250 BCE | attested words; **no sentences** | hieroglyphs |
| `archaic_sumerian` | Archaic Sumerian | Abu Salabikh / Fara tablets, c. 2600-2500 BCE | attested words, composed sentences | cuneiform |
| `old_akkadian` | Old Akkadian | Sargonic royal inscriptions, c. 2350-2150 BCE (oldest written Semitic) | attested words, composed sentences | syllabic cuneiform, sign-by-sign transliteration |
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
| `app/data/ancient/lexicon.json` | Concept lexicon: 35 nouns, 2 adjectives and 17 verbs aligned across all languages, each with a confidence and notes |
| `app/ancient/grammar.py` | One realizer per language: case, agreement, word order, verb conjugation for 8 persons × past/present |
| `app/ancient/parsing.py` | English and Swahili parsers; reverse index for every ancient language and script |
| `app/ancient/scripts.py` | Cuneiform, hieroglyph, fidel, Old Italic, Safaitic and Arabic renderers; every glyph comes from its official Unicode name |
| `app/ancient/engine.py` | Language registry, aliases, `translate()` and `concept_table()` |
| `app/ancient/bridge.py` | Modern languages (French, German, Russian, Chinese, Hebrew, …) to and from the ladder through English with the universal machine translator |
| `app/ancient/quiz.py` | Quizzes for every rung: word meaning, word form and whole sentences |
| `app/ancient/phonetics.py` | IPA and a learner respelling (*say it*) for every rung, with how certain each pronunciation is |

Sentence types: statements (subject, verb, object), **negatives**, **yes/no questions**, and **nominal sentences** with a noun or adjective predicate ("I am a servant", "The king is a servant", "The sun is great"), each in past and present for all eight persons.

Grammar each realizer applies:

- **Sumerian**: SOV, ergative *-e* on transitive subjects, terminative *-še3*, *mu-/ba-* prefixes, *ḫamṭu* (perfective) and *marû* (imperfective) suffix sets, enclitic copula (*lugal-me-en* "I am king", *utu gal-am3* "the sun is great"), negative *nu-* (*nu-mu-un-du3*). Questions are not marked in writing (editorial "?").
- **Egyptian**: VSO, *sḏm.n.f* perfect and *sḏm.f* present, suffix pronouns, independent pronouns (*jnk nswt*), feminine adjective agreement, *mḥ jb* "fill the heart" for *trust*; negation *n sḏm.f* "did not" and *n sḏm.n.f* "does not" (Gardiner §105), questions with *jn*, adjectival sentences (*nfr sw*, *ꜥꜣ rꜥ*) and *A pw B*.
- **Old Latin**: archaic endings (*-os*, *-om*, dative *-ei/-oi/-ai*, perfect *-ei*), verbs governing dative/accusative/*ad*/*in*, SOV; *non*, questions with fronted verb + *-ne*, *nonne*; predicate adjectives agree in gender (*sol magnos est*).
- **Old Arabic**: VSO, case endings and nunation, definite article with sun-letter assimilation, perfect and imperfect conjugation, prepositions *ʿalā*, *bi-*, *ʾilā*; *mā* + perfect, *lā* + imperfect, *hal* / *ʾa-* questions, nominal sentences (*aš-šamsu kabīratun*) and *laysa* with an accusative predicate.
- **Ge'ez**: VSO, *-ku* perfect, accusative *-a*, *ba-* clitic; negative *ʾi-*, question enclitic *-nu*, copular *wəʾətu*.
- **Old Amharic**: SOV, definite *-u/-wa*, accusative *-n*, copula *nəññ/näw*; negative perfect *ʾal-…-m*, negative imperfect *ʾay-…-m*, negative copula *ʾaydälläm*.
- **Old Akkadian**: SOV, cases with mimation (*-um/-am/-im*), uncontracted Old Akkadian vowels (*rabium*), 3rd feminine *ta-* (*tāmur* "she saw"), preterite for the past and durative for the present (full eight-person paradigms written out for every verb), ventive for "come" (*illikam*), *ana/ina* + genitive, adjective predicates as statives (*šarrum rabi* "the king is great", *damqāku* "I am good"), verbless noun sentences (*anāku wardum*), negative *ula*, plural nouns *mû* "water" and *šamû* "heavens" with plural agreement. Cuneiform is spelled with standard syllable signs (CV, VC; *ša-ar-ru-um*); typed input may be normalized (*šarrum*), plain (*sarrum*), sign by sign (*ša-ar-ru-um*) or cuneiform. Akkadian is a separate rung: the Sumerian data and grammar are unchanged, and pasted cuneiform is tried as Sumerian first.
- **Swahili**: noun-class agreement, negative concords (*hakuona*, *haoni*, *sikwenda*), copula *ni/si*, *Je* questions.
- **Proto-Semitic**: reconstructed case vowels and suffix conjugation (*-ku*), prefixed imperfect, negative *\*lā*.

Where a stage has no secure form, it refuses with a reason instead of guessing: negated nominal sentences in Sumerian, Ge'ez, Egyptian and Proto-Semitic; plural adjective agreement where the lexicon has no plural forms; anything beyond roots in Proto-World; anything beyond labels in archaic hieroglyphic.

## Pronunciation

Every result, every word token and every quiz question carries `pronunciation`: an IPA reading, a respelling to read aloud (stressed syllable in capitals) and a note on how certain it is. The *Hear it* buttons and the live guide's voice read the respelling, never raw transliteration with sign numbers.

| Rung | Basis | Example |
|---|---|---|
| Old Akkadian | Reconstructed (comparative Semitic, cuneiform spellings); stress on the last long or closed syllable | *šarrum* SHAR-rum /ˈʃar.rum/, *damqāku* dam-KAA-ku |
| Archaic Sumerian | Approximate (via Akkadian scribes); stress unknown, so not marked | *niĝ-gi-na* ning-gi-na /niŋ.gi.na/ |
| Egyptian | Egyptological classroom convention; IPA shows consonants only | *ꜥnḫ nfr* ankh nefer |
| Old Latin | Restored (c is k, u before a vowel is w); stress not marked because the archaic spelling hides vowel length | *uidit* wi-dit |
| Old Arabic | Classical Arabic; elided article joins the previous word | *tawakkaltu ʿalā l-ḥaqqi* ta-wak-KAL-tu ’A-laal HAK-ki |
| Ge'ez | Traditional church pronunciation (ejective ṣ ṭ q) | *ʾigabra* ’ee-geb-re |
| Old Amharic | Amharic pronunciation of the conservative spelling | *ʾaydälläm* ’ay-del-lem |
| Proto-Semitic | Reconstructed | *\*malku* mal-ku |
| Swahili | Standard; penultimate stress, syllabic m | *Mfalme hakuona mto* m-FAL-me ha-koo-O-na M-to |
| Proto-World | Hypothetical roots, no pronunciation claimed | |

## Modern languages

French, German, Russian, Chinese, Hebrew, Spanish, Portuguese, Italian, Japanese, Hindi, modern Arabic, Korean, Turkish, Persian, Dutch, Ukrainian, Polish, Urdu, Classical Latin and modern Amharic connect to every rung through English:

```text
French ──MT──► English ──► ladder grammar ──► Sumerian, Egyptian, Old Latin, …
Old Latin ──► ladder grammar ──► English ──MT──► Chinese
```

The ancient forms always come from the ladder's grammar, never from the machine translator; each machine-translated step has the status `machine_translation`, and a modern source shows the English it was read as (`bridge.english`). Modern to modern goes directly through the translator. This needs `UNIVERSAL_MT_BASE_URL` (Hy-MT2) or `GOOGLE_CLOUD_TRANSLATE_API_KEY`; without one, modern rows say so instead of failing silently.

## Quizzes

`GET /api/ancient/quiz?language=archaic_sumerian&explain=english|swahili&mode=mixed|meaning|form|sentence&count=10`, and the *Quiz yourself* panel in the Ancient Ladder tab. Sentence questions show a composed sentence; the wrong answers differ from the right one only by negation, tense, person, a noun or the question, and only if the ancient sentence also looks different, so each question can be answered by reading. Archaic hieroglyphic and Proto-World have word quizzes only. The live guide's tutor mode works on any lesson it builds.

## Honesty rules

Every result carries a `status` and a `confidence`:

| Status | Meaning |
|---|---|
| `attested` | A single word found in the language's own texts (spelling may be normalized). |
| `composed` | A sentence built by grammar rules from attested words. It is **not** a quotation of an ancient text. Confidence is capped at 0.75. |
| `reconstructed` / `reconstructed_composition` | Proto-Semitic forms; capped at 0.5. |
| `hypothetical` | Proto-World roots; capped at 0.15. |
| `not_attested_for_this_structure` | The language did not write this kind of sentence (archaic hieroglyphs, Proto-World). Only content-word labels are given, with a `refusal` explanation. |

Gaps are reported, never filled: a concept with no known form in a language comes back as a `gap`. Unknown input words are listed in `parse.unknown_words`, and homographs (Latin *estis*, Sumerian 𒀭 *an/diĝir* and *dù* "build/make", Egyptian 𓏞𓀀 "scribe / I write", vowel-less Safaitic) are listed in `parse.ambiguities`.

Nothing is translated partially in silence. When part of a sentence is outside the grammar (a second object, "of", a plural, an unknown word), the response has `"complete": false`, `parse.not_translated` lists the parts, and `warning` says so in plain words; the browser and the live guide show and say it.

## Using it

API:

```http
GET  /api/ancient/languages                 (ladder languages, modern languages, machine_translation_available)
POST /api/ancient/translate      {"text": "The truth, I have put my trust in", "source": "english", "targets": []}
POST /api/ancient/translate      {"text": "Le roi n'a pas vu le fleuve", "source": "french", "targets": ["archaic_sumerian", "chinese"]}
GET  /api/ancient/quiz?language=middle_egyptian&mode=sentence
GET  /api/ancient/concepts/truth
```

`targets` may name any language ids or aliases (`sw`, `latin`, `ge'ez`, `proto-semitic`, `french`, `zh`, ...); empty means every ancient rung.

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
- Sentences cover one subject, verb and object (with one adjective), negation, yes/no questions and nominal sentences. Second objects, possession ("of"), plural nouns, relative clauses, wh-questions and the future are not modelled yet; they are reported as not translated (the future falls back to the present with a note).
- Not yet ladder stages: Biblical/Paleo-Hebrew, Ugaritic, Phoenician, Hittite, Mycenaean/Homeric Greek, Coptic, Old Babylonian (as distinct from Old Akkadian), Classical Latin and Classical Arabic as separate rungs.
- Akkadian cuneiform uses a standard syllabic spelling; ancient scribes often chose other signs or Sumerian logograms (LUGAL for *šarrum*). Modern Hebrew, Classical Latin and modern Arabic are reachable through the machine-translation bridge.
- Earliest Sumerian and Old Amharic left much grammar unwritten; the fuller later spellings are used and noted per result.
- Display of native scripts depends on installed fonts (Noto Sans Cuneiform, Egyptian Hieroglyphs, Ethiopic, Old Italic and Old North Arabian cover all of them).
