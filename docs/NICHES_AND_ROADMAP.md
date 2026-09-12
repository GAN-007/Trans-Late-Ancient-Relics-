# Niche Opportunities and Product Roadmap

Ancient Egyptian translation sits at the intersection of language technology, computer vision, education, archaeology, museums, accessibility and knowledge provenance. The project can therefore grow beyond a conventional translator.

## High-value niches

### Museum and heritage interpretation

Point a device at an exhibit label or inscription and show sign identification, transliteration, literal translation, natural translation, cultural notes and source confidence. A museum deployment can lock the app to approved object collections and institution-reviewed interpretations.

### Archaeological field assistant

A tablet/phone workflow can photograph an inscription, preserve object/site metadata, segment lines, compare readings, attach researcher notes and queue uncertain signs for later review. Offline on-device OCR is a major future differentiator for excavations with poor connectivity.

### Epigraphy and damaged-text reconstruction

Rather than output one sentence, the engine can model lacunae, uncertain signs, alternative restorations and confidence per sign/word. This is closer to how real scholarship works than consumer OCR.

### Comparative historical linguistics

Add Old, Middle and Late Egyptian, Demotic and Coptic layers so a user can trace lexical and phonological evolution. Coptic evidence can inform pronunciation hypotheses without falsely implying certainty.

### Education and adaptive tutoring

Use learner error patterns, spaced repetition, sign recognition games, listening practice, grammar drills and personalized lesson recommendations. The current progress data model is a foundation for this.

### Swahili-first African heritage technology

Most Egyptology tools are English-centric. A strong Swahili academic vocabulary layer can make Egyptian language learning more accessible in East Africa while preserving Egyptological terminology.

### Accessibility

Speech recognition, read-aloud, high-contrast modes, large glyph cards, keyboard control and descriptive sign names can make visual/linguistic material usable by more learners.

### AR translation overlay

A future native/PWA vision model can draw boxes over recognized signs and place transliteration/translation above each sign group in real time.

### Scholarly corpus annotation

Institutions can import inscriptions with provenance, period, object ID, museum accession, bibliography and accepted transliterations. Reviewer decisions then become auditable corpus annotations rather than opaque model weights.

### Restoration and conservation

Image enhancement, multispectral photography and comparison against known parallel texts can support reading faint or damaged signs while keeping original and enhanced imagery linked.

### Tourist and cultural guide

A simplified mode can explain visible signs, names and concepts at archaeological sites, while a scholar mode exposes the uncertainty and grammar underneath.

### Conversational historical-language laboratory

The app can generate constrained pedagogical Middle Egyptian dialogues, clearly marking reconstructed classroom speech versus attested written forms. Learners could practice questions, titles, offerings and simple narratives with contextual feedback.

## Technical roadmap

### Phase A — implemented in v2

- camera preview and auto-scan transport;
- speech input and read-aloud;
- context/intent-aware candidate output;
- user roles and reviewed community lexicon;
- AI/vision gateway contracts;
- daily review-gated research option;
- PWA/device support;
- feedback/unresolved-term loop.

### Phase B — next

- complete Gardiner/Unicode sign database;
- biliteral/triliteral and determinative models;
- sentence morphology/parser;
- sign bounding boxes and line segmentation;
- object/inscription provenance schema;
- import/export of scholarly annotations;
- spaced repetition scheduler;
- server-side speech fallback;
- rate limiting and PostgreSQL deployment profile.

### Phase C — research-grade

- hieroglyph object-detection model trained on photographs rather than clean fonts;
- damaged-sign probabilistic restoration;
- period/genre-aware language model constrained by corpus evidence;
- Coptic phonological evidence graph;
- EHFC sign-block renderer/editor;
- collaborative line-by-line inscription workspace;
- museum collection connectors;
- offline mobile inference.

## Non-goal

The product should never become a system that hides uncertainty behind a fluent sentence. For ancient languages, exposing uncertainty, evidence and alternatives is a core feature, not a weakness.
