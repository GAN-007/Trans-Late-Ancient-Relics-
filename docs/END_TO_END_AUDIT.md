# End-to-End Audit and v2 Rebuild

## Executive summary

The pre-v2 repository had a sound educational principle: keep the modern ESHB encoding layer separate from historical Middle Egyptian. Its strongest code was the reversible strict-token ESHB mechanism and the explicit refusal to call unverified word substitution authentic Egyptian.

Its main weakness was product completeness. It was a text-only single-page utility with no identity model, no permission system, no camera or voice workflow, no contextual conversation state, no live vision adapter, no reviewed runtime vocabulary growth, no opt-in history, and very little device/accessibility behavior beyond one mobile breakpoint.

v2 keeps the original linguistic safety boundary and rebuilds the surrounding product into a multimodal language-learning platform.

---

## 1. Repository audit before v2

### `app/eshb.py`

**What worked**

- strict separators made the modern ESHB encoding recoverable;
- Swahili digraphs were represented explicitly;
- unsupported orthographic and IPA characters used reversible escape tokens;
- IPA used longest-token matching for affricates such as `tʃ` and `dʒ`;
- the earlier `/r/` versus `/ɾ/` collision had already been corrected.

**Limitations**

- ESHB was intentionally orthographic, not semantic; users could easily confuse it with authentic Egyptian without strong UI separation;
- there was no device-level pronunciation practice;
- no copy/share/history tooling existed.

**v2 decision**

Keep the codec intact, move it to a clearly labelled Script Lab, and add a separate speech layer.

### `app/egyptian.py`

**What worked**

- core uniliteral table was explicit and inspectable;
- MdC conversion handled the special consonant symbols;
- canonical/logographic teaching spellings were distinguished from uniliteral fallback;
- unknown signs were surfaced rather than ignored.

**Limitations**

- lexicon was static at process start;
- only uniliteral reverse parsing was implemented;
- no reviewed runtime overlay;
- no sign-function parser for biliterals, triliterals, determinatives or quadrat layout.

**v2 decision**

Add request-time reviewed lexicon overlays. Keep the uniliteral parser explicitly limited instead of pretending a full epigraphic parser exists.

### `app/translator.py`

**What worked**

- exact dictionary lookup was conservative;
- a small set of grammar templates existed;
- unsupported sentences returned lexical analysis instead of fake full translation;
- Egyptian-to-modern output labelled itself a lexical gloss.

**Limitations**

- only a handful of phrase templates existed;
- phrase context and speaker intent were absent;
- exact dictionary selection picked a first match without a real discourse ranking model;
- modern proper names could leak into fallback hieroglyph rendering as if they were Egyptian transliteration;
- no conversation-aware alternative ranking;
- no automatic capture of repeated unknown vocabulary.

**v2 decision**

Add a contextual orchestration layer that preserves deterministic evidence, records unresolved terms and optionally asks a multimodal/text model to rank interpretations. Modern names are kept separate from authentic Egyptian spelling.

### `app/pedagogy.py` and lesson data

**What worked**

- 26 lessons covered the correct progression from sign mechanics through grammar and inscription analysis;
- quizzes were simple and understandable;
- SQLite progress persistence existed.

**Limitations**

- progress used an arbitrary learner string rather than authenticated ownership;
- any caller could request another arbitrary learner's progress;
- no spoken lesson examples;
- no adaptive review or spaced repetition.

**v2 decision**

Bind progress writes/reads to authenticated users and add read-aloud buttons. A future spaced-repetition scheduler is documented as a next step.

### `app/main.py`

**What worked**

- API was small and easy to understand;
- existing ESHB/script/dictionary endpoints were clean;
- static frontend and API ran from one deployable service.

**Limitations**

- no authentication/authorization;
- no camera/image endpoint;
- no contextual/AI endpoint;
- no history, audit or review APIs;
- no security headers;
- no abuse controls;
- no lifecycle task for knowledge enrichment.

**v2 decision**

Retain existing endpoints and add auth, contextual translation, vision, speech reading, history, knowledge governance, AI status and a controlled background proposal loop.

### `app/static/index.html`, `app.js`, `styles.css`

**What worked**

- lightweight dependency-free UI;
- basic mobile stacking;
- dictionary, lessons and script tools were discoverable.

**Limitations**

- no microphone/camera interaction;
- translation output was raw JSON rather than a human-first explanation;
- one horizontal nav had no capability status or account state;
- no permission-aware UI;
- no PWA manifest/service worker;
- no safe-area handling for phones;
- no accessibility/status regions for long-running media actions;
- no image upload alternative for desktops/research scans;
- no read-aloud control.

**v2 decision**

Rebuild the SPA around Translate, Live Lens, Talk, Learn, Dictionary, Script Lab, Knowledge and About. Add PWA shell, device capability detection, touch-friendly controls, live status, accessible focus states, safe-area handling and reduced-motion support.

### Deployment and CI

**What worked**

- Docker and CI already tested Python 3.11–3.13;
- Docker build was verified;
- runtime progress storage had been moved into a mounted directory.

**Limitations**

- container ran as root;
- no AI/auth configuration documentation;
- production cookie behavior was not separated from localhost developer behavior.

**v2 decision**

Run the container as an unprivileged user, consolidate runtime state into one SQLite database, document environment settings, keep local Compose cookies non-secure, and require secure cookies in HTTPS production.

---

## 2. v2 system layers

### Layer A — reversible representation

- English ⇄ ESHB
- Swahili ⇄ ESHB
- IPA ⇄ ESHB

This layer is algorithmic. It is not historical translation.

### Layer B — historical writing mechanics

- uniliteral values;
- selected canonical/logographic forms;
- MdC special-character conversion;
- transliteration rendering;
- explicit fallback/unknown handling.

### Layer C — lexical and grammatical analysis

- trilingual lexicon;
- phrase templates;
- ambiguity exposure;
- lexical candidate lists;
- no silent invention.

### Layer D — contextual interpretation

- user-supplied discourse context;
- output register: literal, natural, scholarly, learner;
- optional AI ranking of deterministic candidates;
- unverified suggestions clearly flagged.

### Layer E — multimodal access

- camera capture;
- live sampled-frame analysis;
- image upload;
- speech-to-text where the browser supports it;
- live completed-utterance translation for conversation mode;
- text-to-speech/read-aloud;
- front/rear camera switching where hardware supports it;
- classroom Ancient Egyptian pronunciation.

### Layer F — learning and knowledge governance

- lessons;
- quizzes;
- authenticated progress;
- learner translation ratings/corrections for reviewer inspection;
- unresolved-term telemetry;
- contributor proposals;
- reviewer approval;
- optional daily AI drafts that never auto-approve.

---

## 3. User roles and authorization

### Guest

Can use the learning and translation product without creating an account. No personal history or server-side progress is stored.

### Learner

Owns progress and optional history. Cannot change shared linguistic knowledge.

### Contributor

Can submit proposed lexicon, grammar, sign or pronunciation changes with evidence.

### Reviewer

Can inspect unresolved vocabulary and approve/reject knowledge proposals.

### Admin

Can manage roles and manually run the AI draft loop.

The server enforces permissions. UI hiding is convenience, not the security boundary.

---

## 4. Device and interaction audit

### Phones

Primary field/museum device. The UI supports portrait/landscape, rear-camera preference, `playsinline`, large touch controls, safe-area insets, responsive one-column cards and PWA installation.

### Tablets

Useful for museum tours, classrooms and archaeology field notes. Two-column layouts become one column below 900 px; camera preview remains 4:3 and lesson navigation becomes non-sticky when needed.

### Desktop/laptop

Research-first use: large translation panels, dictionary/sign tables, image upload, keyboard navigation, reviewer queue and admin role controls.

### Low-bandwidth devices

Live Lens offers low-detail frames and compresses images before submission. The static shell is cached. AI and fresh dynamic data still require connectivity.

### Accessibility

- keyboard focus styling;
- semantic labels and live regions;
- read-aloud translation;
- voice input when available;
- reduced-motion support;
- typing/OS dictation fallback when browser speech recognition is absent;
- no meaning is communicated only by animation or color.

---

## 5. Context, nuance and “lost in translation” strategy

One ancient expression can map to several modern meanings; one modern sentence can require different Egyptian structures depending on speaker, register, period, genre and discourse focus.

The platform therefore stores/returns:

- deterministic lexical candidates;
- grammatical mode/template;
- alternative meanings;
- ambiguity notes;
- user-supplied context;
- preferred interpretation and rationale when AI review is enabled;
- confidence rather than binary certainty;
- unverified-form warnings.

The AI layer is not allowed to overwrite the evidence layer. It ranks and explains; proposed new forms go through the knowledge-review workflow.

---

## 6. AI learning loop

A self-modifying dictionary would be unsafe: one hallucinated form could become future “evidence” and reinforce itself. v2 uses a controlled loop instead:

```text
failed / partial translation
        ↓
record unresolved term + context + frequency
        ↓
periodic top-unresolved selection
        ↓
AI drafts candidate lemma and bilingual glosses
        ↓
pending proposal
        ↓
human evidence review
   ↙ reject     approve ↘
no change       runtime reviewed overlay
```

The loop can run every 24 hours but is disabled by default. Approval remains human.

---

## 7. Live vision pipeline

```text
camera or uploaded image
        ↓
browser resize/compress
        ↓
server MIME/base64/signature/size validation
        ↓
optional multimodal model
        ↓
script detection
reading direction
sign/Gardiner candidates
transliteration candidates
translation candidates
uncertainties
        ↓
visual result + optional speech output
```

Frames are not stored by the application.

A dedicated Egyptological OCR/sign-recognition model remains future research work. General-purpose multimodal analysis is treated as candidate generation, not proof.

---

## 8. Niches and product directions

The platform can support far more than a “translator” screen:

1. **Museum visitor guide** — point a phone at a stela and get layered explanations.
2. **Archaeology field assistant** — capture damaged signs, preserve candidate readings and notes.
3. **Epigraphy workstation** — compare transliterations, Gardiner signs and uncertainty.
4. **Classroom tutor** — lessons, quizzes, pronunciation and teacher-led review.
5. **Accessibility reader** — spoken explanations for users who cannot easily inspect dense sign text.
6. **Heritage tourism** — location-specific artifact stories without flattening meaning.
7. **Conservation/restoration** — compare partially damaged signs and potential restorations.
8. **Lexicography** — reviewed multilingual lemma expansion.
9. **Corpus annotation** — object-level source provenance, genre and period tags.
10. **Translation memory** — retrieve prior analyzed constructions and comparable phrases.
11. **Semantic graph** — connect roots, derivations, determinatives, concepts and contexts.
12. **Palaeography** — compare sign shape variants across periods/hands.
13. **Cross-script Egyptian** — hieratic, demotic and Coptic extensions.
14. **Pronunciation research** — layer Coptic and comparative evidence without pretending certainty.
15. **Named-entity/titulary analysis** — royal names, epithets, offices and genealogies.
16. **Formula recognition** — offering formulae, funerary sequences and standard titulary.
17. **Damaged-text hypothesis ranking** — alternate restorations with confidence and evidence.
18. **Research collaboration** — contributor/reviewer workflow and audit trail.
19. **Multilingual Africa-facing education** — Swahili-first Egyptology rather than English-only access.
20. **AR overlay** — future sign-by-sign labels on top of a live camera view.
21. **Artifact catalog integration** — museum object IDs and provenance metadata.
22. **Academic benchmark platform** — compare model predictions with reviewed gold readings.
23. **Children's discovery mode** — controlled simplified explanations while preserving scholarly notes.
24. **Tour guide mode** — short spoken summaries plus optional deep analysis.
25. **Research export** — TEI/EpiDoc/JSON-LD compatible annotation in a future layer.
26. **Cultural knowledge graph** — connect gods, places, titles, objects and concepts to attestations.
27. **Sign handwriting practice** — trace/recognize learner-drawn signs.
28. **Pronunciation coaching** — compare learner audio to the chosen classroom convention.
29. **Offline expedition packs** — preloaded lexicon/lessons for low-connectivity sites.
30. **Community evidence review** — scholarly moderation rather than crowd-vote truth.

The v2 architecture implements the shared foundations for these niches: multimodal input, context, permissions, reviewed knowledge overlays, PWA behavior and explicit uncertainty.

---

## 9. Remaining high-value implementation gaps

These should be treated as research milestones, not cosmetic TODOs:

1. complete sign inventory and sign-value graph;
2. Unicode Egyptian Hieroglyph Format Controls/quadrat layout;
3. dedicated computer-vision sign detector and segmenter;
4. training data for degraded stone/papyrus/painted surfaces;
5. biliteral/triliteral + phonetic-complement decoding;
6. determinative classification;
7. Middle Egyptian morphological analyzer/generator;
8. syntactic parser beyond teaching templates;
9. period/genre-sensitive language model;
10. attestation database with source provenance;
11. robust proper-name/foreign-name transcription;
12. hieratic/demotic/Coptic modules;
13. scholar-reviewed evaluation set;
14. PostgreSQL/object storage/queue architecture for multi-instance scale;
15. WebSocket/Realtime channel if sub-second continuous multimodal interaction becomes necessary.

v2 intentionally exposes these boundaries rather than masking them with a generic AI response.
