# v3 End-to-End Gap Audit — Linguistics, Epigraphy, Vision, Voice and Research Governance

This document audits the repository after the v2 multimodal rebuild and records the v3 changes made in response to a deeper review of Ancient Egyptian translation, phonetics, sign function, live interaction and evolutionary research.

## Executive verdict

The project has a strong product foundation and one especially important design principle: **ESHB is a modern reversible representation system, while authentic Ancient Egyptian is a historical language that must be interpreted through signs, morphology, syntax, context and evidence.** That separation must never be weakened.

The v2 application was already substantially better than a decorative “A → bird” translator: it had a reviewed learner lexicon, uncertainty labels, contextual AI review, user roles, camera capture, browser speech, lessons, human-reviewed knowledge proposals and CI. However, several capabilities were interfaces rather than complete research systems. In particular:

- live camera analysis was periodic HTTP frame submission to a general multimodal model, not a dedicated epigraphic detector;
- reverse script parsing recognized only uniliterals;
- there was no Unicode quadrat/control parser;
- morphology was not formally exposed as an analysis layer;
- pronunciation had a classroom convention but no separate consonantal reconstruction view;
- there was no governed vision-correction dataset loop;
- live conversation had continuous browser speech input but no stateful low-latency server channel;
- the lexicon had useful glosses but little structured attestation/provenance metadata;
- a full period-aware Middle Egyptian grammar/parser remains research work.

v3 closes the **software loop** around those gaps without falsely claiming that the remaining Egyptological research has been solved.

---

# 1. Review of the proposed external architecture

The suggested Next.js + OpenCV/ONNX + phoneme-WAV + SQLAlchemy + Airflow topology contained useful ideas, but several parts needed correction before implementation.

## 1.1 Next.js is not required to solve the linguistic problem

The current dependency-light SPA is already responsive, installable and connected to FastAPI. Rewriting it in Next.js would add a Node build/runtime and migration cost without improving sign recognition, historical grammar or phonological evidence. v3 therefore keeps the current frontend and implements the missing transport/research layers directly.

A Next.js migration can still be justified later if server-side rendering, route-level code splitting, a large component ecosystem or organization-wide React standardization becomes a concrete requirement.

## 1.2 500 ms HTTP frame polling is not an appropriate default

Two frames per second sent as base64 HTTP requests is expensive on mobile data, wastes inference capacity, increases heat/battery use and can create overlapping work when inference is slower than capture. v3 replaces continuous polling with a WebSocket channel whose client sends the next frame **only after the previous result returns**. This creates natural backpressure.

Manual capture/upload keeps the normal HTTP endpoint as a robust fallback.

## 1.3 A detector must not sort all signs left-to-right and call that Egyptian reading order

Egyptian can be written right-to-left or left-to-right, vertically, and in grouped quadrats. Direction is often indicated by the orientation/facing of people, animals or other signs. Pure `(y, x)` sorting can produce a plausible-looking but false reading.

The local detector therefore emits low-confidence geometric LTR/RTL hypotheses and explicitly leaves reading direction unresolved until orientation/layout evidence is available.

## 1.4 ONNX is useful infrastructure, not a substitute for a trained epigraphic model

v3 adds an optional ONNX/OpenCV adapter, letterbox preprocessing, common detector-output parsing, class-aware NMS, model hashing and a class-map contract. It does **not** ship fake weights. A reliable model requires a licensed, annotated corpus and an Egyptologist-reviewed benchmark.

INT8 quantization is supported as an operational recommendation only after calibration and accuracy testing; it is not automatically “better” because it is faster.

## 1.5 Phoneme-WAV concatenation should not be labelled authentic Ancient Egyptian speech

Hieroglyphic Egyptian normally omits vowels. Concatenating modern phoneme clips can generate a useful accessibility/teaching voice but cannot recover missing historical vowels by itself. v3 therefore separates:

- modern Egyptological classroom reading;
- broad consonantal IPA reconstruction candidates;
- a research profile that states which evidence is required before proposing historical vocalization.

Actual historical pronunciation research needs date/period, lexeme identity, morphology, Coptic evidence where relevant and published comparative reconstruction.

## 1.6 Active learning must not auto-promote a model at an arbitrary correction count

“Once 1,000 rows are approved, retrain and automatically replace the model” is unsafe. It can create feedback loops, class imbalance, duplicated near-identical video frames, provenance problems and silent regression.

v3 implements correction capture and reviewed dataset export, but **automatic retraining and automatic production model promotion are both disabled by design**. A candidate model must pass a frozen benchmark and human review before staged rollout.

## 1.7 SQLAlchemy/PostgreSQL is an eventual scale decision, not a prerequisite for correctness

The current SQLite/WAL layer is appropriate for a single-node educational/self-hosted deployment and keeps the repository easy to run. A multi-replica production deployment should migrate user/session/research data to PostgreSQL and move rate limiting to a shared store or trusted gateway. v3 documents that boundary rather than pretending SQLite is horizontally scalable.

---

# 2. Root-level file audit

## `.github/workflows/ci.yml`

**Purpose:** compile/test on Python 3.11, 3.12 and 3.13, validate API import, check browser JavaScript syntax and build Docker.

**v3 change:** version assertion is upgraded to 3.0.0; epigraphy/morphology smoke checks are added; matrix remains multi-version and Docker remains downstream of tests.

**Remaining:** add dependency vulnerability scanning, SBOM generation, container image scanning and a separate optional-vision job once a distributable model exists.

## `.gitignore` / `.dockerignore`

Keep transient databases, secrets, environments and local build state out of source/container context.

**Remaining:** if model weights are large or licensed separately, explicitly ignore local checkpoints and distribute them through a model registry rather than Git.

## `ARCHITECTURE.json`

Machine-readable architecture summary from v2.

**Remaining:** update alongside every major capability/version so it does not drift from README/API reality; v3 should describe WebSockets, epigraphy and active-learning governance.

## `Dockerfile`

Already runs as a non-root user and includes a health check.

**Remaining:** optional local vision requires either a separate image/profile with `requirements-vision.txt` or a multi-stage target. Do not force OpenCV/ONNX into the lightweight base image when a deployment uses only hosted multimodal vision.

## `docker-compose.yml`

Good for a single-node persistent runtime database.

**Remaining:** production topology needs TLS/reverse proxy, backup policy, external database if replicated, secret injection and resource limits.

## `Makefile`

Developer convenience commands.

**Remaining:** add optional vision install/model validation and research-dataset QA targets when those workflows stabilize.

## `requirements.txt`

Intentionally light core runtime.

## `requirements-vision.txt` — v3

Adds optional NumPy/OpenCV/ONNX Runtime dependencies without bloating deployments that do not use local inference.

## `pyproject.toml`

v3 version metadata and core dependencies.

## `README.md`

Product boundary, architecture, setup and research limitations.

**v3 requirement:** must continue to state that model plumbing is not equivalent to a trained/validated epigraphic model.

## `SANITY_CHECK.json`

A lightweight project snapshot from earlier versions.

**Remaining:** either update automatically from CI or remove it; manually maintained generated-looking status files become stale easily.

## `LICENSE`

Software license only. It does **not** grant rights to third-party corpora, museum images or dictionaries used later for research/training.

---

# 3. Backend module audit

## `app/__init__.py`

Package version. v3 sets `3.0.0`.

## `app/eshb.py`

**Strong:** deterministic reversible modern bridge, escape tokens, Swahili digraphs, IPA longest-token parsing, `/r/` vs `/ɾ/` separation.

**Do not change:** ESHB must remain visibly distinct from authentic Ancient Egyptian.

**Remaining:** better Unicode grapheme handling for unusual modern text and formal versioning of the ESHB codebook so old encoded strings remain decodable after future codebook changes.

## `app/egyptian.py`

**Strong:** core uniliterals, selected canonical spellings, MdC special values, safe fallback warnings, reviewed runtime lexicon overlay.

**Gap:** reverse parsing still only guarantees uniliterals. Historical spellings involving multi-consonant signs, classifiers/determinatives and alternative orthographies need sign-function analysis.

**v3 complement:** `epigraphy.py` adds sign-function candidates and Unicode layout/control recognition instead of overloading this simple renderer.

## `app/epigraphy.py` — v3

Introduces:

- Egyptian Hieroglyph Unicode block detection;
- Egyptian Hieroglyph Format Control separation;
- Egyptian Hieroglyphs Extended-A detection;
- reviewed teaching-core sign metadata;
- phonogram/logogram/determinative candidate classification;
- candidate phonetic-complement detection;
- damage/lost-sign control reporting;
- explicit warning that Unicode order alone does not determine original reading direction.

**Still missing:** a complete licensed Unikemet/Gardiner catalog, sign variants, orientation metadata, true quadrat parse tree, word segmentation and corpus-conditioned function disambiguation.

## `app/morphology.py` — v3

Exposes a conservative teaching morphology layer:

- suffix pronouns;
- common particles/prepositions;
- `sḏm.n.f`-type pattern recognition;
- suffix-pronoun ambiguity (subject vs possessor vs complement);
- clause hints without pretending to be a complete parser.

**Still missing:** verb classes, weak verbs, participles, relative forms, stative/person paradigms, nominal/adjectival agreement, negation systems, diachrony, syntactic dependency analysis and discourse-aware tense/aspect interpretation.

## `app/translator.py`

**Strong:** refuses unsupported “full” translation and exposes lexical analysis instead.

**Critical gap:** the historical translator is still a small learner engine. It cannot yet parse arbitrary Middle Egyptian inscriptions.

**Research path:** build a lemma/morphology/syntax pipeline backed by an attested corpus; use AI only to rank/explain evidence, not fabricate unattested Egyptian.

## `app/contextual.py`

v2 already separated deterministic evidence from optional AI review.

**v3 enhancements:** morphological analysis for Egyptian source text, evidence tiers/confidence ceilings, clarification questions and separate pronunciation evidence.

**Remaining:** richer conversation discourse model, speaker/addressee features, genre/period/provenance constraints and sentence-level syntactic candidates.

## `app/speech.py`

v2 provided safe classroom reading.

**v3 enhancements:** classroom IPA, consonantal IPA candidates with per-symbol uncertainty, and a research profile that explicitly refuses to invent historical vowels.

**Remaining research:** lexeme-specific historical vocalization data with citations, period-sensitive sound changes, Coptic descendant mappings, prosodic reconstruction and a speech synthesizer trained/labelled for pedagogical reconstruction rather than falsely “authentic” speech.

## `app/ai.py`

**Strong:** structured JSON requests, cautious prompts, AI suggestions marked unverified, no automatic knowledge approval.

**Gap:** general multimodal reasoning is not a deterministic OCR engine and can hallucinate Gardiner IDs.

**v3 mitigation:** hybrid/local evidence streams can be compared; disagreements are surfaced rather than hidden.

**Remaining:** schema validation of model output beyond “JSON object”, provider retry/circuit-breaker logic, cost telemetry, evaluation harness and prompt/model versioning.

## `app/vision.py`

v2 validated image transport and delegated recognition to multimodal AI.

**v3 enhancements:** backend selection (`auto`, `local`, `ai`, `hybrid`), image SHA, local/AI status, hybrid disagreement reporting and strict separation of detector confidence from linguistic confidence.

## `app/vision_local.py` — v3

Optional OpenCV/ONNX inference adapter with:

- lazy optional imports;
- model/class-map validation;
- model SHA-256 version identity;
- letterbox preprocessing instead of distortion;
- common ONNX detector tensor parsing;
- confidence filtering and class-aware NMS;
- mapping detections back to original image coordinates;
- explicitly non-authoritative reading-order hypotheses.

**Missing by design:** actual production weights and a complete class map. Those are research assets, not code placeholders.

## `app/active_learning.py` — v3

Closes the camera-correction loop:

- signed-in users can submit a correction to a machine analysis;
- image retention requires explicit consent **and** a deployment feature flag;
- otherwise only an image hash is retained when an image is supplied;
- reviewers approve/reject corrections;
- admins can export approved metadata as a dataset manifest;
- the manifest states benchmark/promotion gates;
- no automatic retraining or model promotion.

**Remaining:** object storage with lifecycle policy, annotation UI/bounding boxes, dataset licensing metadata, duplicate detection, artifact/source IDs, experiment tracking and an external trainer/model registry.

## `app/auth.py`

**Strong for current scale:** scrypt, random opaque sessions stored hashed, HttpOnly/SameSite cookies, server-enforced roles.

**v3:** permissions add vision correction/review/dataset boundaries; expired sessions cleaned at startup.

**Remaining at enterprise scale:** email/SSO/MFA, account recovery, audit log, refresh/session management UI, PostgreSQL, organization/tenant scoping and formal migration tooling.

## `app/security.py`

v2 had CSP, permissions policy and in-memory limits.

**v3:** cross-origin resource policy, production HSTS and browser Origin checking for unsafe HTTP requests.

**Remaining:** distributed rate limiting, trusted proxy configuration, security event logging and external penetration/dependency scanning.

## `app/streaming.py` — v3

Adds same-origin WebSockets for:

- live vision with per-connection rate limits and sequential processing/backpressure;
- conversational translation with a short in-memory context trace;
- no streaming-layer persistence.

**Remaining:** binary frame transport to avoid base64 overhead, adaptive resolution based on latency/network, worker queues/GPU scheduling and horizontal WebSocket scaling.

## `app/knowledge.py`

Good human-review boundary for lexicon/sign/grammar/pronunciation proposals. AI lexicon approval requires reviewer evidence/source URL.

**Major remaining data gap:** evidence is mostly free text + one URL. A scholarly knowledge graph should model source/work, object/text ID, line/context, period, provenance, spelling variant, lemma ID, sense ID, contributor and review history separately.

## `app/learning_loop.py`

Good rule: AI can draft, never approve.

**Remaining:** avoid treating frequency alone as research priority; include uncertainty, learner impact, source quality and reviewer capacity in prioritization.

## `app/feedback.py`

Useful general user feedback channel.

**v3 complement:** vision corrections now have their own structured review queue instead of overloading free-text feedback.

## `app/history.py`

Opt-in authenticated translation history.

**Remaining:** retention/deletion controls per item, export, encryption/backups policy and organization-level privacy controls if deployed institutionally.

## `app/pedagogy.py`

Good 26-lesson foundation and basic quizzes.

**Remaining:** spaced repetition, adaptive item scheduling, sign recognition exercises, pronunciation comparison, mastery prerequisites, teacher dashboards and research-backed distractor generation.

## `app/runtime.py`

SQLite WAL and shared runtime path are good for simple deployment.

**Remaining:** explicit migration/version table and PostgreSQL adapter for multi-instance scale.

## `app/models.py`

Pydantic API boundary.

**v3:** pronunciation profile and active-learning correction/review schemas.

**Remaining:** stricter schemas for knowledge-proposal payload variants and multimodal AI response validation.

## `app/main.py`

v3 becomes the integration layer for epigraphy, morphology, pronunciation, vision backend status, WebSockets and governed corrections while retaining v2 APIs.

**Remaining:** split routers by domain as API surface grows; `main.py` will otherwise become a maintenance bottleneck.

---

# 4. Frontend and PWA audit

## `app/static/index.html`

Strong information architecture: Translate, Live Lens, Talk, Learn, Dictionary, Script Lab, Knowledge, About.

**Remaining:** dedicated epigraphy workbench for bounding boxes/quadrat groups, side-by-side candidate readings, artifact metadata and reviewer correction tools. Current v3 correction UI is deliberately lightweight.

## `app/static/js/camera.js`

Good rear-camera preference, switching, canvas resizing and browser-native capture.

**Remaining:** device selection by `deviceId`, torch/zoom/focus controls where supported, rotation/orientation metadata and ROI cropping.

## `app/static/js/lens.js`

v2 used a 2.6-second interval and HTTP requests.

**v3:** live mode uses WebSocket/backpressure, manual HTTP remains, result UI exposes sign/determinative/complement candidates and authenticated users can submit research corrections with explicit image-consent control.

**Remaining:** draw bounding boxes directly over video, region selection, stabilization across consecutive frames and track IDs so repeated frames are not treated as independent evidence.

## `app/static/js/speech.js`

Uses browser speech recognition/synthesis with graceful fallback.

**Limitation:** browser speech services differ by platform and may use vendor cloud services. The application should never imply that microphone audio is processed locally merely because the app server receives only transcripts.

## `app/static/js/talk.js`

**v3:** live utterances use a stateful WebSocket conversation when available, with HTTP fallback; short context survives within the socket only.

**Remaining:** interruption/barge-in, turn-taking/VAD, streamed ASR/TTS, latency metrics and optional on-device ASR.

## `app/static/js/translate.js`

Human-first rendering of deterministic and AI interpretation layers.

**Remaining:** make evidence tiers/clarification prompts more visually prominent and expose morphology trees for scholarly mode.

## `app/static/js/learn.js`

Lesson rendering/progress.

**Remaining:** adaptive/spaced repetition and richer media exercises.

## `app/static/js/account.js`

Authentication and role-aware knowledge controls.

**Remaining:** account/session security controls and dedicated reviewer workspace as queues grow.

## `app/static/js/core.js`

Shared device capabilities/state/API helpers.

**Remaining:** centralized event/state architecture if UI complexity grows; current small global state is acceptable for this SPA size.

## `app/static/js/api.js`

Simple fetch wrapper.

**Remaining:** typed/schema-generated client, request IDs and retry policy for idempotent operations.

## `app/static/js/app.js`

v3 boot logic updates displayed version/privacy wording without a framework migration.

## `app/static/service-worker.js`

v3 cache key and app-shell caching; API remains network-backed.

**Remaining:** no offline historical corpus/dictionary pack yet. If implemented, version data packs separately from the app shell.

## `app/static/styles.css`, `icon.svg`, `manifest.webmanifest`

Responsive PWA presentation.

**Remaining:** visual bounding-box overlay styles and institutional/theming support are product enhancements, not linguistic blockers.

## `app/static/app.js`

Legacy pre-module frontend artifact. It is no longer loaded by `index.html` and should be removed to avoid maintainers editing the wrong file.

---

# 5. Data audit

## `app/data/lexicon/01.json` … `09.json`

The learner lexicon contains useful English/Swahili glosses, parts of speech, notes, confidence and selected canonical spellings.

**Critical research gap:** “confidence: high” is not a citation. A research-grade lexicon needs structured provenance:

- stable lemma/sense ID;
- normalized transliteration and orthographic variants;
- period/date range;
- dialect/register/genre;
- object/text/source reference;
- line/context attestation;
- sign spelling(s) and determinatives;
- morphology/valency for verbs;
- English/Swahili translation senses separately;
- bibliography/license;
- reviewer/version history.

Swahili needs the same sense-level discipline as English; it should not merely be a second gloss list appended after an English analysis.

## `app/data/lessons/01_foundation.json` … `04_advanced.json`

Good structured learner progression.

**Remaining:** cite claims/examples at lesson-item level, distinguish conventional pronunciation from reconstruction on every audio item, and add inscription objects with provenance/image rights.

## `app/data/references.json`

Useful source list but not yet an attestation graph. It should evolve into structured source metadata consumed by lexicon/grammar/sign records.

---

# 6. Testing audit

## `tests/test_core.py`

Protects ESHB/IPA reversibility, MdC conversion, canonical rendering, uniliteral parsing and data counts.

## `tests/test_v2.py`

Protects auth/RBAC, knowledge governance, privacy-safe vision fallback, PWA/security headers and AI proposal review boundaries.

## `tests/test_v3.py`

Adds regression coverage for:

- Unicode format controls and Extended-A detection;
- phonetic-complement candidate analysis;
- `sḏm.n.f`-type morphology;
- classroom vs consonantal/historical pronunciation boundaries;
- missing-model behavior without fake inference;
- active-learning consent and no automatic model promotion;
- correction permissions and browser-origin hardening;
- WebSocket vision/conversation paths;
- v3 API endpoints.

**Remaining:** real image/model tests require a distributable model and licensed fixture set. Add golden epigraphic cases and Egyptologist-reviewed expected analyses rather than only software-level unit tests.

---

# 7. Miscommunication / misunderstanding loop

The target loop is now:

```text
camera / text / speech
        ↓
raw evidence
        ↓
sign / lexical / morphological candidates
        ↓
explicit ambiguity + confidence + unresolved items
        ↓
context questions / human clarification
        ↓
translation candidates
        ↓
learner/researcher feedback
        ↓
reviewed correction / proposal queue
        ↓
source/evidence review
        ↓
approved knowledge or approved dataset item
        ↓
benchmark/training candidate
        ↓
human-gated model/knowledge promotion
```

The key principle is that **uncertainty is information**. The system should ask for missing period, genre, nearby signs or intended sense instead of hiding those unknowns behind a fluent sentence.

---

# 8. Research priorities after v3

## Priority 0 — scholarly data model

Before scaling AI, introduce stable lemma/sense/sign/source/attestation IDs and provenance fields. This is the highest-leverage step because every translator, evaluator and learner feature depends on reliable evidence.

## Priority 1 — corpus-backed morphology/syntax

Use a legally reusable, lemmatized/morphologically annotated corpus where licensing permits. Build deterministic analyzers/generators and evaluate them independently of LLM fluency.

## Priority 2 — complete sign catalog + quadrat engine

Integrate a complete licensed Unikemet/Gardiner mapping, format controls, sign variants/orientation and quadrat trees. The Unicode controls already recognized in v3 provide the technical foundation but not the catalog.

## Priority 3 — dedicated epigraphic vision model

Train/evaluate on artifact-level splits, damaged inscriptions, varying lighting/materials, multiple scripts/styles and sign variants. Report per-class calibration and “unknown” behavior.

## Priority 4 — historical phonology

Build a cited reconstruction layer by period/lexeme rather than generic vowel insertion. Coptic is important evidence but should not be mechanically projected backward as if all stages shared the same vocalization.

## Priority 5 — hieratic, Demotic and Coptic

Treat these as separate script/language stages with shared historical links, not merely additional fonts for the hieroglyphic engine.

## Priority 6 — institutional research workflow

PostgreSQL, object storage, immutable audit log, DOI/object IDs, reviewer assignments, corpus licensing metadata, model registry, experiment tracking and benchmark dashboard.

---

# 9. What v3 now truthfully claims

v3 can provide a real-time **translation assistance workflow**: capture/stream a frame, identify sign candidates when a configured vision backend exists, expose candidate sign functions/readings, surface uncertainty, translate reviewed known material, speak pedagogical output, accept human corrections and preserve a governed path toward better models.

v3 does **not** claim that arbitrary damaged Ancient Egyptian can already be translated with Egyptologist-level reliability from a camera. Achieving that requires the research assets listed above. The architecture now makes those missing assets explicit and gives them safe integration points instead of masking them with fluent but unsupported output.
