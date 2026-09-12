# End-to-End Audit — Trans-Late Ancient Relics

## Scope

This audit covers the repository as it existed before the v2 rebuild: FastAPI backend, ESHB encoder/decoder, Middle Egyptian lexicon and script helpers, translator, pedagogy/progress, browser UI, tests, Docker/CI and the interaction model.

## What v1 already did well

- It correctly separated modern reversible ESHB encoding from historical Middle Egyptian translation.
- ESHB English/Swahili and IPA round trips were deterministic when strict separators were preserved.
- Middle Egyptian canonical/logographic forms could be returned from the curated teaching lexicon, with uniliteral spelling clearly labelled as fallback.
- The code included transliteration ↔ MdC helpers, uniliteral parsing, a trilingual dictionary, lessons, quizzes and SQLite progress.
- Unsupported historical sentences were not blindly presented as authentic Egyptian.
- The repository had tests, Docker packaging and CI.

## Material gaps found in v1

### Translation logic

The translator was intentionally narrow. It relied on a small dictionary and five regex grammar templates. It did not perform intent classification, morphology beyond simple lexical splitting, discourse/context ranking, alternative candidate generation, provenance tracing, feedback capture or user-correctable translations. Egyptian → English/Swahili returned a first lexical gloss even when several senses existed.

### Historical language depth

The sign engine covered uniliterals and selected canonical dictionary glyphs but not a complete sign catalogue, biliteral/triliteral parser, determinative classifier, phonetic-complement resolver, EHFC/MdC block layout, period-aware morphology, syntax parser, royal titulary, Coptic evidence or corpus attestations.

### GUI and interaction

The interface was a seven-tab static form application. It had no camera, microphone, read-aloud, live mode, translation history, candidate comparison, confidence visualization, context/intent controls, account flow, permissions UI or contribution/review workflow.

### Devices

The CSS was responsive at one breakpoint, but the product had no PWA manifest, service worker, camera-specific mobile layout, touch-oriented bottom navigation, safe-area support, capability detection, install flow or explicit browser/device feature fallbacks.

### Identity and permissions

There were no users, sessions or roles. Progress accepted an arbitrary learner string. There was no privacy boundary between users, no contributor/reviewer/admin workflow and no audit trail.

### AI and vocabulary growth

There was no AI provider interface, no live vision path, no context-aware second pass, no unresolved-term counter and no governed vocabulary growth loop. Adding vocabulary meant manually editing repository JSON.

### Accessibility and speech

There was no speech recognition, speech synthesis, camera-permission explanation, keyboard skip link, capability report or explicit historical-pronunciation disclaimer tied to read-aloud.

### Operational gaps

The service had no user-management schema, translation history, feedback tables, reviewer queue, audit events, external AI configuration contract or scheduled research loop.

## v2 rebuild response

The rebuild adds:

1. Responsive PWA interface with desktop/tablet/mobile layouts.
2. Explicit camera Live Lens with manual and automatic frame analysis.
3. Device speech recognition and speech synthesis where supported.
4. Conventional Egyptological classroom read-aloud endpoint, explicitly separated from historical pronunciation.
5. Candidate-based translation responses with confidence, assumptions, ambiguity and provenance.
6. Context and intended-speech-act input plus automatic intent heuristics.
7. Basic Egyptian morphological analysis for suffix-pronoun notation and prepositional forms.
8. User accounts and database-backed sessions.
9. Role hierarchy: guest → learner → contributor → reviewer → admin.
10. Per-user progress and translation history.
11. Translation feedback and unresolved-term collection.
12. Review-gated vocabulary proposals and reviewed community lexicon additions.
13. Vendor-neutral text-AI and vision-AI gateway contracts.
14. Optional daily AI research loop that creates pending proposals but never self-approves.
15. Audit logging for security- and knowledge-changing actions.
16. PWA manifest, service worker, offline app shell and local guest progress.
17. Stronger device capability reporting and permission transparency.
18. Expanded automated tests for auth, roles, lexicon review, context, morphology, live vision gating and IPA reversibility.

## Remaining research-grade gaps

The rebuild deliberately does **not** claim that unrestricted Ancient Egyptian machine translation is solved. Research-grade next steps remain:

- complete Gardiner + Unicode + MdC + EHFC sign catalogue;
- biliteral/triliteral recognition and sign-function disambiguation;
- object-detection/segmentation model specifically trained on hieroglyphic inscriptions;
- period-aware Middle Egyptian morphology and syntax;
- corpus-attested orthographic variants with source IDs and dates;
- royal names/titulary and damaged-text reconstruction;
- Coptic/phonological evidence layer;
- true sign-block composition and bidirectional layout;
- server-side STT/TTS for browsers without Web Speech support;
- offline on-device vision model for archaeological field use;
- institution-grade SSO, rate limiting and external database support for large deployments.

The product now exposes those limits instead of silently crossing them.
