# Trans-Late Ancient Relics

**Trans-Late Ancient Relics** is an Ancient Egyptian learning and translation platform built around a strict separation between:

1. **ESHB** — a modern reversible bridge for English, Swahili and IPA using Egyptian hieroglyphic Unicode signs as an encoding layer; and
2. **Middle Egyptian** — the historical language, where signs can be phonograms, logograms, determinatives or phonetic complements and where translation requires morphology, syntax and context.

Version **2.0** expands the original tutor into a multimodal, accessible platform with contextual translation, live camera capture, spoken interaction, an installable PWA shell, user roles and a human-reviewed AI knowledge loop.

## What v2 can do

- English ⇄ strict/display ESHB
- Swahili ⇄ ESHB with CH, SH, DH, TH, KH, GH, NY, NG and NG'
- IPA ⇄ ESHB with reversible Unicode fallback
- Egyptological transliteration ⇄ core hieroglyph rendering
- Manuel de Codage ⇄ Egyptological transliteration for core special consonants
- Middle Egyptian ⇄ English/Swahili learner lexicon
- contextual translation that exposes ambiguity instead of hiding it
- conventional classroom pronunciation for accessibility, clearly separated from historical reconstruction
- browser speech recognition for English/Swahili input when the device supports it
- optional live conversation mode that translates each completed utterance and can speak the reply
- browser speech synthesis for read-aloud output
- live camera capture, front/rear camera switching and periodic live scanning
- image upload for desktop/museum/archival workflows
- optional multimodal AI analysis of relic images
- 26 structured Middle Egyptian lessons
- vocabulary quiz and learner progress
- authenticated history and learner correction feedback
- guest, learner, contributor, reviewer and admin permission layers
- human-reviewed lexicon proposals
- optional daily AI proposal loop driven by repeated unresolved terms
- responsive mobile/tablet/desktop UI
- installable Progressive Web App shell
- Docker packaging and GitHub Actions CI

## Critical accuracy principle

The application never equates authentic Egyptian translation with replacing A–Z letters by pictures.

Historical translation follows this conceptual path:

```text
English / Swahili meaning
        ↓
semantic interpretation + discourse context
        ↓
Middle Egyptian lexical candidates
        ↓
morphology
        ↓
syntax
        ↓
Egyptological transliteration
        ↓
historical orthographic candidates
        ↓
phonograms + logograms + complements + determinatives
        ↓
hieroglyphic rendering
```

Reverse inscription analysis is:

```text
image / inscription
        ↓
reading direction + sign segmentation
        ↓
Gardiner/sign identification
        ↓
sign-function analysis
        ↓
transliteration candidates
        ↓
word segmentation + morphology
        ↓
syntax + context
        ↓
ranked English / Swahili meanings
```

When the evidence is insufficient, the platform reports uncertainty instead of manufacturing certainty.

## Architecture

```text
Browser / PWA
├── contextual text translator
├── Live Lens camera
├── Talk / speech interface
├── lessons and dictionary
├── ESHB + IPA + MdC script lab
└── contributor/reviewer knowledge UI
        │
        ▼
FastAPI
├── auth.py             users, roles, sessions
├── contextual.py       deterministic + optional AI nuance layer
├── translator.py       lexicon and grammar templates
├── egyptian.py         transliteration/sign tools + runtime lexicon overlay
├── eshb.py             reversible ESHB and IPA encoding
├── speech.py           classroom pronunciation
├── vision.py           validated image pipeline
├── ai.py               optional multimodal/contextual provider adapter
├── pedagogy.py         lessons, quizzes, progress
├── history.py          opt-in authenticated translation history
├── feedback.py         learner ratings/corrections for reviewer inspection
├── knowledge.py        proposals, review, unresolved-term queue
└── learning_loop.py    daily AI drafts; never auto-approves knowledge
        │
        ▼
SQLite runtime database
```

## Permission model

| Role | Capabilities |
|---|---|
| Guest | translate, camera, voice, dictionary, lessons, ESHB/IPA/script tools |
| Learner | guest capabilities + saved progress/history/feedback |
| Contributor | learner capabilities + submit lexicon/grammar/sign proposals |
| Reviewer | contributor capabilities + inspect unresolved terms and approve/reject proposals |
| Admin | reviewer capabilities + manage user roles and manually run AI knowledge cycles |

The first registered account is **not** automatically an admin. For a self-hosted instance, bootstrap an admin with environment variables shown below.

## Live camera and AI

Camera access happens in the browser through `getUserMedia`. The app captures compressed JPEG frames and sends them only when the user captures an image or enables live scanning.

The application itself does **not** persist camera frames. When an external AI provider is configured, that provider receives the submitted frame for analysis. The current optional adapter uses the OpenAI Responses API with image input. The server keeps the API key private; it is never sent to the browser.

Without an AI key, the camera and upload interfaces still operate and validate frames, but the backend reports that vision recognition is not configured instead of faking OCR.

## Voice

- **Speech input:** uses the browser's `SpeechRecognition`/`webkitSpeechRecognition` implementation when present. English uses `en-US`; Swahili requests `sw-KE`.
- **Speech output:** uses browser `speechSynthesis`.
- **Ancient Egyptian:** the app speaks a conventional Egyptological classroom reading, not a claim about exact Middle Kingdom pronunciation.

Speech recognition support varies by browser and platform. The UI detects capability and keeps typing/OS dictation as fallback.

## Human-reviewed AI learning loop

The system records unresolved words encountered in failed translations. If the knowledge loop is enabled, an AI provider can periodically draft candidate lexicon entries for the most frequent unresolved terms.

AI drafts are stored as **pending proposals**. They do not enter the live dictionary until a reviewer/admin explicitly approves them. The design intentionally prevents autonomous hallucinations from silently becoming linguistic truth.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

Run checks:

```bash
make check
```

## Docker

```bash
docker compose up --build
```

The Compose file persists SQLite runtime data in a named volume.

## Optional AI configuration

```bash
export ESHB_AI_PROVIDER=openai
export OPENAI_API_KEY='...'
export ESHB_AI_MODEL='gpt-5.6'
```

Optional knowledge loop:

```bash
export ESHB_KNOWLEDGE_LOOP_ENABLED=true
export ESHB_KNOWLEDGE_LOOP_HOURS=24
export ESHB_KNOWLEDGE_LOOP_BATCH=5
```

Bootstrap an administrator on first startup:

```bash
export ESHB_BOOTSTRAP_ADMIN_USERNAME=admin
export ESHB_BOOTSTRAP_ADMIN_PASSWORD='use-a-long-unique-password'
export ESHB_BOOTSTRAP_ADMIN_DISPLAY_NAME='Administrator'
```

For HTTPS production deployments:

```bash
export ESHB_ENV=production
export ESHB_SECURE_COOKIES=true
```

Never commit `.env` or API keys.

## PWA and device support

The responsive browser interface targets:

- phones in portrait or landscape;
- tablets used in classrooms, museums or field archaeology;
- desktop/laptop research workstations;
- touch and mouse/keyboard interaction;
- installed PWA use where supported.

Camera/microphone access generally requires a secure context (`https://`) except on `localhost`.

The service worker caches only the application shell. Translation, authentication, AI analysis and fresh dictionary overlays remain network-backed.

## API highlights

```text
POST /api/translate/contextual
POST /api/vision/analyze
POST /api/speech/classroom-reading
POST /api/auth/register
POST /api/auth/login
POST /api/feedback
GET  /api/auth/me
GET  /api/dictionary
GET  /api/lessons
POST /api/knowledge/proposals
PUT  /api/knowledge/proposals/{id}/evidence
POST /api/knowledge/proposals/{id}/review
POST /api/knowledge/loop/run
```

Existing ESHB, IPA, MdC and deterministic translation endpoints remain available for compatibility.

## Data and copyright

The repository contains an original educational core lexicon and lesson curriculum. It is **not** a substitute for a professional Egyptological dictionary or a fully attested corpus.

When expanding the dictionary, store provenance and use sources whose licensing permits the intended use. Do not scrape copyrighted dictionaries into the repository.

## Documentation

- [`docs/END_TO_END_AUDIT.md`](docs/END_TO_END_AUDIT.md) — code/UI/logic audit and v2 rebuild decisions
- [`docs/USER_JOURNEYS.md`](docs/USER_JOURNEYS.md) — device, role and workflow journeys
- [`docs/SECURITY_PRIVACY.md`](docs/SECURITY_PRIVACY.md) — camera, microphone, sessions, AI and data handling
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — environment variables and deployment settings

## Remaining research-grade work

The v2 platform now has the interfaces and governance required for a serious product, but unrestricted historical translation still needs substantial scholarly data and models:

- complete Unicode/Gardiner/MdC sign inventory;
- biliteral/triliteral sign recognition and phonetic-complement parsing;
- determinative classifier;
- period-aware Middle Egyptian morphology and syntax;
- sign-quadrat layout engine using Egyptian Hieroglyph Format Controls;
- source-attested lemma database with period, genre and object provenance;
- training/evaluation corpus for damaged inscriptions and alternative restorations;
- hieratic/demotic/Coptic expansion;
- dedicated vision model for epigraphy rather than general-purpose image reasoning;
- evaluation benchmarks reviewed by Egyptologists.

Those are explicit next layers, not hidden limitations.
