# Trans-Late Ancient Relics

**Trans-Late Ancient Relics v3** is an evidence-aware Ancient Egyptian learning, epigraphy and translation platform. Its core design rule is that two different systems must never be confused:

1. **ESHB** — a modern, algorithmically reversible English/Swahili/IPA bridge that uses hieroglyphic Unicode signs as an encoding alphabet; and
2. **Historical Egyptian** — a language and writing system in which signs can be phonograms, logograms, determinatives, phonetic complements or layout elements, and where translation requires morphology, syntax, context and evidence.

v3 extends the v2 multimodal platform with a real epigraphy-analysis layer, optional local ONNX vision, WebSocket live camera/conversation paths, pronunciation evidence profiles and a privacy-gated human correction loop for future model research.

## What v3 can do

- English ⇄ strict/display ESHB
- Swahili ⇄ ESHB with CH, SH, DH, TH, KH, GH, NY, NG and NG'
- IPA ⇄ ESHB with reversible Unicode fallback
- Egyptological transliteration ⇄ core hieroglyph rendering
- Manuel de Codage ⇄ core Egyptological transliteration symbols
- Middle Egyptian ⇄ English/Swahili learner lexicon
- contextual translation with alternatives, clarification questions and evidence ceilings
- rule-based teaching morphology including suffix-pronoun and `sḏm.n.f`-type analysis
- Unicode Egyptian Hieroglyph sign detection
- Egyptian Hieroglyph Format Control recognition for layout/damage metadata
- Egyptian Hieroglyphs Extended-A detection
- candidate phonogram/logogram/determinative/phonetic-complement analysis
- conventional classroom pronunciation plus a separate consonantal IPA research aid
- browser speech recognition for English/Swahili where supported
- browser speech synthesis/read-aloud
- stateful WebSocket conversation translation with HTTP fallback
- rear/front live camera capture and image upload
- WebSocket live camera analysis with backpressure instead of fixed 500 ms polling
- optional local OpenCV/ONNX sign detector adapter
- optional multimodal AI vision
- hybrid local/AI evidence comparison with disagreement reporting
- signed-in research corrections with human review
- image retention only under explicit user consent **and** server policy
- no automatic retraining or automatic model promotion
- 26 structured Middle Egyptian lessons, quizzes and progress
- guest, learner, contributor, reviewer and admin permission layers
- human-reviewed knowledge proposals and optional AI draft loop
- responsive PWA, Docker and Python 3.11–3.13 CI

## Accuracy boundary

This project does not create authentic Egyptian by mapping English letters to birds or snakes.

Historical forward translation conceptually requires:

```text
English / Swahili meaning
        ↓
intent + discourse + register
        ↓
Middle Egyptian lexical senses
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
quadrat/layout representation
```

Reverse inscription analysis requires:

```text
artifact image / encoded inscription
        ↓
region + sign detection
        ↓
orientation / reading-direction hypotheses
        ↓
sign grouping + quadrats
        ↓
phonogram / logogram / determinative / complement candidates
        ↓
transliteration candidates
        ↓
word segmentation + morphology
        ↓
syntax + period/genre/context
        ↓
ranked English / Swahili interpretations
```

v3 implements more of this pipeline than v2, but it still reports unresolved research layers rather than inventing certainty.

## Architecture

```text
Browser / PWA
├── Contextual Translate
├── Live Lens
│   ├── manual HTTP capture/upload
│   └── WebSocket live stream with backpressure
├── Talk
│   ├── browser speech recognition
│   ├── WebSocket conversation context
│   └── speech synthesis
├── Learn / Dictionary
├── Script Lab
└── Knowledge / correction workflows
          │
          ▼
FastAPI v3
├── eshb.py              reversible modern bridge
├── egyptian.py          core transliteration/rendering + lexicon overlay
├── epigraphy.py         Unicode/sign-function/layout candidates
├── morphology.py        conservative teaching morphology
├── translator.py        deterministic lexicon/templates
├── contextual.py        evidence tier + optional AI ranking
├── speech.py            classroom + consonantal pronunciation profiles
├── vision.py            backend orchestration / hybrid evidence
├── vision_local.py      optional OpenCV/ONNX detector adapter
├── ai.py                optional multimodal/text reviewer
├── streaming.py         live vision/conversation WebSockets
├── active_learning.py   governed vision correction/dataset manifest
├── knowledge.py         linguistic proposals/review
├── learning_loop.py     optional AI drafts, never auto-approved
├── auth.py              users/sessions/RBAC
├── pedagogy.py          lessons/quizzes/progress
├── history.py           opt-in translation history
├── feedback.py          learner feedback
└── security.py          CSP/origin checks/rate controls
          │
          ▼
SQLite/WAL runtime data for single-node deployments
```

## Permission model

| Role | Capabilities |
|---|---|
| Guest | translate, camera, voice, dictionary, lessons, script/epigraphy tools |
| Learner | guest + progress/history/feedback + submit vision corrections |
| Contributor | learner + linguistic knowledge proposals |
| Reviewer | contributor + review knowledge/vision corrections and inspect research queues |
| Admin | reviewer + manage roles, run AI draft cycles and export approved dataset manifests |

The server enforces these permissions; hiding UI controls is not the security boundary.

## Live camera vision

### Hosted multimodal backend

```bash
export ESHB_AI_PROVIDER=openai
export OPENAI_API_KEY='...'
export ESHB_AI_MODEL='gpt-5.6'
export ESHB_VISION_BACKEND=ai
```

### Local ONNX backend

The repository contains the inference adapter but intentionally does not contain fabricated model weights.

```bash
pip install -r requirements-vision.txt
export ESHB_VISION_BACKEND=local
export ESHB_VISION_MODEL_PATH=/models/relic_detector.onnx
export ESHB_VISION_CLASSES_PATH=/models/classes.json
```

See [`models/README.md`](models/README.md).

### Hybrid mode

```bash
export ESHB_VISION_BACKEND=hybrid
```

When local and AI candidates disagree, the API exposes that disagreement. Neither source silently overwrites the other.

### Reading direction

The detector does **not** claim that left-to-right bounding-box order is Egyptian reading order. It returns low-confidence geometric hypotheses; sign orientation/facing and epigraphic context must establish direction.

## Live transport

The Live Lens uses:

```text
WS /ws/vision
```

A new frame is sent only after the previous result arrives. This avoids request pile-ups and reduces mobile bandwidth/heat compared with fixed high-frequency polling.

Conversation mode uses:

```text
WS /ws/conversation
```

It retains only a short in-memory meaning trace for that socket. The streaming layer does not persist conversation turns.

## Pronunciation

Three concepts are kept separate:

- **classroom reading** — modern Egyptological convention, useful for learners/accessibility;
- **consonantal IPA skeleton** — broad candidate consonant values with uncertainty;
- **historical reconstruction** — not produced automatically without period/lexeme/comparative evidence.

Example endpoint:

```http
POST /api/speech/pronunciation
{
  "text": "nfr sḏm",
  "profile": "research"
}
```

The API explicitly states that unwritten vowels have not been reconstructed.

## Research correction / active-learning loop

Ordinary camera frames are transient. A signed-in learner/researcher may submit a correction after a bad result:

```text
machine analysis
      ↓
user/researcher correction
      ↓
pending correction
      ↓
reviewer approve/reject
      ↓
approved dataset manifest
      ↓
external dataset QA / training / benchmark
      ↓
human-gated model promotion
```

Image retention is disabled by default:

```bash
export ESHB_ACTIVE_LEARNING_STORE_IMAGES=false
```

If an institution enables it, the individual correction still requires explicit user consent.

The application never triggers model training or swaps production weights automatically merely because a row-count threshold has been reached.

See [`docs/V3_RESEARCH_MODEL_GOVERNANCE.md`](docs/V3_RESEARCH_MODEL_GOVERNANCE.md).

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

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

The base container stays lightweight and does not install local computer-vision dependencies. Build a vision-specific image/profile when using ONNX/OpenCV.

## Environment highlights

```bash
# Runtime
export ESHB_ENV=production
export ESHB_SECURE_COOKIES=true

# Optional AI
export ESHB_AI_PROVIDER=openai
export OPENAI_API_KEY='...'
export ESHB_AI_MODEL='gpt-5.6'

# Vision routing
export ESHB_VISION_BACKEND=auto        # auto | local | ai | hybrid
export ESHB_VISION_MODEL_PATH=/models/relic_detector.onnx
export ESHB_VISION_CLASSES_PATH=/models/classes.json
export ESHB_VISION_CONFIDENCE=0.45
export ESHB_VISION_NMS_IOU=0.45

# Active-learning privacy
export ESHB_ACTIVE_LEARNING_ENABLED=true
export ESHB_ACTIVE_LEARNING_STORE_IMAGES=false

# Knowledge draft loop
export ESHB_KNOWLEDGE_LOOP_ENABLED=false
export ESHB_KNOWLEDGE_LOOP_HOURS=24
export ESHB_KNOWLEDGE_LOOP_BATCH=5

# Bootstrap administrator
export ESHB_BOOTSTRAP_ADMIN_USERNAME=admin
export ESHB_BOOTSTRAP_ADMIN_PASSWORD='use-a-long-unique-password'
```

Never commit secrets, `.env` files, private datasets or restricted model weights.

## v3 API highlights

```text
POST /api/translate/contextual
POST /api/egyptian/analyze-signs
POST /api/egyptian/analyze-transliteration
GET  /api/egyptian/epigraphy-capabilities
POST /api/speech/pronunciation
GET  /api/vision/status
POST /api/vision/analyze
WS   /ws/vision
WS   /ws/conversation
POST /api/vision/corrections
GET  /api/vision/corrections
POST /api/vision/corrections/{id}/review
GET  /api/research/collection-policy
GET  /api/research/dataset-manifest
```

Existing ESHB, IPA, MdC, dictionary, lesson, auth, history, feedback and knowledge endpoints remain available.

## Documentation

- [`docs/V3_GAP_AUDIT.md`](docs/V3_GAP_AUDIT.md) — complete code/logic/data/product gap audit and v3 decisions
- [`docs/V3_RESEARCH_MODEL_GOVERNANCE.md`](docs/V3_RESEARCH_MODEL_GOVERNANCE.md) — correction, dataset, training and model-promotion rules
- [`docs/END_TO_END_AUDIT.md`](docs/END_TO_END_AUDIT.md) — v2 audit/history
- [`docs/USER_JOURNEYS.md`](docs/USER_JOURNEYS.md) — roles/devices/workflows
- [`docs/SECURITY_PRIVACY.md`](docs/SECURITY_PRIVACY.md) — security/privacy model
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — deployment configuration

## Remaining research-grade work

The most important unsolved areas are now explicit:

- source-attested lemma/sense database with period, genre, object and line provenance;
- complete licensed Gardiner/Unikemet sign catalog and variants;
- full quadrat/group parser and layout renderer;
- period-aware morphology/syntax, not only teaching patterns;
- dedicated epigraphic vision weights and a licensed benchmark;
- damaged-text restoration with uncertainty distributions;
- historical vocalization data grounded in comparative/Coptic evidence;
- hieratic, Demotic and Coptic layers;
- artifact-level multilingual evaluation for English and Swahili;
- PostgreSQL/object storage/audit/model registry for institutional multi-node use.

v3 supplies safe integration points for those layers without claiming they already exist.
