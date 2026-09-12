# Trans-Late Ancient Relics

**Trans-Late Ancient Relics** is a live, context-aware Ancient Egyptian learning and translation platform built around a strict separation between modern reversible encoding and historical language analysis.

The application combines:

- English ⇄ ESHB hieroglyphic bridge;
- Swahili ⇄ ESHB, including Swahili digraphs;
- IPA ⇄ ESHB;
- Egyptological transliteration, MdC and core hieroglyphic sign tools;
- a trilingual Middle Egyptian learner lexicon;
- 26 structured lessons and quizzes;
- context/intent-aware translation candidates with confidence, ambiguity and provenance;
- camera-based live translation transport;
- microphone input and read-aloud;
- accounts, roles, translation history and synchronized progress;
- a review-gated community lexicon;
- a human-in-the-loop AI vocabulary growth process;
- PWA/mobile/tablet/desktop support;
- FastAPI, SQLite, CLI, Docker and GitHub Actions CI.

## The core linguistic rule

Ancient Egyptian is not an A–Z picture cipher. Hieroglyphic writing can use one-, two- and three-consonant phonograms, logograms, phonetic complements and semantic determinatives. Vowels are normally not written in the way modern English or Swahili writes them.

Accordingly the product exposes two different systems:

1. **ESHB** — a modern reversible bridge for English/Swahili/IPA.
2. **Middle Egyptian** — a historical-language layer with explicit uncertainty, grammar, transliteration and reviewed lexical evidence.

## v2 headline features

### Live Lens

The browser can open the device camera after explicit user permission. A user can analyze a single frame or enable automatic repeated analysis. Camera frames are only sent to a configured vision endpoint while analysis is active.

Configure a vision gateway with:

```text
ESHB_VISION_ENDPOINT=https://your-ai-gateway.example/v1/vision
ESHB_VISION_API_KEY=secret
```

If no vision provider is configured, the app says so. It does not fabricate OCR output.

### Speak and read aloud

Where the browser exposes Web Speech Recognition, users can speak English or Swahili, edit the transcript and send it through the same translation pipeline as typed text.

Browser speech synthesis can read results aloud. When the output is Egyptian transliteration, the app first produces an **Egyptological classroom reading** and explicitly labels it as conventional rather than exact historical pronunciation.

### Context-aware translation

The translation request can include:

- source and target language;
- surrounding context;
- intended speech act or meaning;
- literal/natural/careful mode;
- optional AI second-pass review.

Responses can contain multiple candidates with:

- transliteration;
- hieroglyphs;
- literal and natural translation;
- confidence;
- rationale;
- assumptions;
- ambiguities;
- provenance.

Unsupported sentences remain analysis-only instead of being presented as authentic Egyptian.

### Human-reviewed AI growth

Unknown terms are counted. Users can submit translation feedback. Contributors can propose lexical entries. Reviewers can approve or reject them. Approved entries join the runtime community lexicon without changing the static teaching data.

AI can also propose research candidates, but **AI cannot approve its own suggestions**.

Optional scheduled research:

```text
ESHB_AUTO_RESEARCH_ENABLED=true
ESHB_AUTO_RESEARCH_INTERVAL_HOURS=24
ESHB_AUTO_RESEARCH_MIN_FREQUENCY=3
```

### Roles

The hierarchy is:

```text
guest → learner → contributor → reviewer → admin
```

- Guest: deterministic translation, ESHB, lessons, dictionary, local speech/read-aloud, camera preview.
- Learner: synchronized progress, history and configured cloud vision.
- Contributor: propose lexicon entries.
- Reviewer: approve/reject entries and run knowledge-loop research.
- Admin: manage roles/disabled users and inspect audit events.

See `docs/SECURITY_AND_PERMISSIONS.md` for the full matrix.

## Translation architecture

Modern bridge:

```text
English / Swahili / IPA
        ↓
normalization + tokenization
        ↓
ESHB logical units
        ↓
strict reversible representation
        ↓
hieroglyphic display representation
```

Historical translation:

```text
English / Swahili meaning
        ↓
intent + context
        ↓
lexical candidates
        ↓
Middle Egyptian morphology
        ↓
syntax / grammar
        ↓
Egyptological transliteration
        ↓
historical spelling candidates
        ↓
phonograms / logograms / complements / determinatives
        ↓
candidate ranking + confidence + provenance
```

Historical reverse analysis:

```text
image / inscription
        ↓
reading direction
        ↓
sign segmentation + candidate Gardiner IDs
        ↓
sign function analysis
        ↓
transliteration candidates
        ↓
word segmentation + morphology
        ↓
syntax
        ↓
lexical sense disambiguation
        ↓
English / Swahili candidates
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Windows activation:

```powershell
.venv\Scripts\activate
```

Open:

```text
http://127.0.0.1:8000
```

API docs:

```text
http://127.0.0.1:8000/docs
```

## Docker

```bash
docker compose up --build
```

For production HTTPS, set:

```text
ESHB_SECURE_COOKIES=true
```

## Bootstrap administrator

```text
ESHB_ADMIN_EMAIL=admin@example.com
ESHB_ADMIN_PASSWORD=use-a-long-random-secret
ESHB_ADMIN_NAME=Administrator
```

Do not commit real credentials.

## AI gateway

The repository is deliberately vendor-neutral. Configure any compatible internal/external model gateway with:

```text
ESHB_AI_ENDPOINT=https://your-ai-gateway.example/v1/review
ESHB_AI_API_KEY=secret
ESHB_VISION_ENDPOINT=https://your-ai-gateway.example/v1/vision
ESHB_VISION_API_KEY=secret
```

See `docs/AI_LIVE_TRANSLATION.md` for request/response expectations.

## CLI

```bash
python cli.py encode "Habari yako" --lang swahili
python cli.py decode "𓉔·𓄿·𓃀·𓄿·𓂋·𓇋"
python cli.py ipa-encode "hɑbari"
python cli.py hiero "nfr pr"
python cli.py dict "nzuri" --lang swahili
python cli.py translate "I am a scribe" --source english --target egyptian --context "self introduction"
python cli.py pronounce "nfr"
python cli.py morphology "rn.j"
```

## Tests

```bash
make check
```

The suite covers ESHB/IPA reversibility, translation safeguards, context intent, morphology, pronunciation disclaimers, accounts, permissions, progress, translation history, contribution/review workflow and live-vision provider gating.

## Important documentation

- `docs/AUDIT.md` — end-to-end analysis of the previous implementation and what v2 changes.
- `docs/USER_JOURNEYS.md` — 70 user and operational journeys.
- `docs/SECURITY_AND_PERMISSIONS.md` — account/session/role model.
- `docs/AI_LIVE_TRANSLATION.md` — live camera, speech and AI contracts.
- `docs/NICHES_AND_ROADMAP.md` — museum, archaeology, epigraphy, education, accessibility and research opportunities.
- `docs/DEVICE_MATRIX.md` — expected behavior across phones, tablets and desktop browsers.

## Remaining research-grade work

This repository does **not** claim unrestricted Ancient Egyptian machine translation is solved. Major future work includes:

- complete Gardiner/Unicode/MdC/EHFC sign inventory;
- biliteral/triliteral and determinative parsing;
- a photograph-trained hieroglyph detector and line segmenter;
- period-aware morphology and syntax;
- attestation/corpus provenance per spelling and sense;
- damaged-text restoration with uncertainty;
- Coptic evidence for phonological reconstruction;
- true hieroglyphic block composition;
- offline/on-device vision;
- server-side STT/TTS fallback;
- institution-scale PostgreSQL/SSO/rate limiting.

Those limits are part of the product contract: the app should expose uncertainty instead of hiding it behind fluent-looking output.
