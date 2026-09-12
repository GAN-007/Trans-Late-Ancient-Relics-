# v3 Research, Dataset and Model Governance

Ancient Egyptian translation is a high-uncertainty historical-language problem. A model can be fluent while wrong. This document defines the rules that keep research corrections, AI proposals and future vision models from feeding errors back into the product.

## Evidence classes

Use these conceptual tiers in data/model work:

1. **Primary artifact/text evidence** — photographed or published inscription with stable object/text reference and legal reuse basis.
2. **Scholarly edition/corpus evidence** — edited reading, transliteration, morphology or translation from a citable source.
3. **Reviewed project knowledge** — a project contributor/reviewer has mapped evidence into the repository schema and recorded provenance.
4. **Machine candidate** — detector/LLM/parser proposal awaiting verification.
5. **Learner/user suggestion** — valuable signal but not historical evidence until reviewed.

Machine confidence must never be presented as if it were scholarly attestation.

## Vision correction policy

The `/api/vision/corrections` workflow records:

- machine analysis;
- proposed human correction;
- context;
- model/version identity where known;
- optional image hash;
- optional retained image only when both user consent and deployment policy permit it;
- review status/note/reviewer.

Default behavior does **not** store camera images.

### Why hashes are useful

A SHA-256 can help identify repeated submissions without retaining the original bytes. It is not an anonymization guarantee if an operator already possesses candidate source images; treat hashes as research metadata, not as proof of privacy.

## Image retention

Enable only where the institution has a reason, retention policy and legal basis:

```bash
export ESHB_ACTIVE_LEARNING_STORE_IMAGES=true
```

The UI must still collect explicit consent per correction. A server flag alone is insufficient.

For serious institutional use, move retained images from the local runtime folder to controlled object storage with:

- encrypted transport/storage;
- per-object provenance/license fields;
- restricted researcher access;
- retention/deletion policy;
- immutable access/audit log;
- backups consistent with deletion obligations.

## Annotation requirements

A training-quality sign annotation should eventually contain:

- image/artifact/source ID;
- bounding polygon or box;
- sign catalog ID(s);
- glyph/variant/orientation;
- damaged/uncertain/illegible state;
- group/quadrat membership;
- candidate reading/function;
- annotator/reviewer IDs;
- source/license;
- disagreement history.

A single corrected sentence is not enough to train a sign detector.

## Preventing frame leakage

Live camera frames are highly correlated. Randomly placing neighboring frames into train and test sets will inflate apparent accuracy.

Split by **artifact/object/source session**, not by individual frame. All images of the same inscription/object should normally stay in one split.

## Training trigger

There is deliberately no `if approved_count >= N: retrain()` logic in the application.

A training run should be started by an external MLOps process after a curator/researcher declares a dataset version ready. The manifest endpoint provides governed metadata but does not launch a trainer.

## Candidate-model evaluation

Before a model can be considered for promotion, evaluate at least:

- per-sign precision, recall and F1;
- confidence calibration / reliability curves;
- rare-sign performance;
- unknown/out-of-distribution behavior;
- damaged/partial sign performance;
- material/lighting/domain shifts;
- reading-sequence downstream accuracy;
- impact on translation accuracy, not only detector mAP;
- latency/memory on intended phones/servers;
- subgroup/source leakage checks.

A detector that recognizes common signs while confidently hallucinating rare ones can be more dangerous than a conservative detector with lower recall.

## Champion/challenger promotion

Recommended production path:

```text
approved dataset version
       ↓
reproducible training run
       ↓
candidate model + immutable metadata
       ↓
frozen offline benchmark
       ↓
human review of disagreements/failures
       ↓
staging / shadow traffic
       ↓
limited canary
       ↓
production promotion
       ↓
continuous error monitoring
```

Every promotion must have an immediate rollback target.

## Quantization

INT8/FP16 optimization is evaluated **after** the unquantized candidate is validated. Quantization needs a representative calibration set. Measure the accuracy delta; do not make latency the only acceptance criterion.

## AI knowledge proposals

The existing unresolved-term loop may create a draft lexicon proposal. Rules remain:

- AI cannot approve its own proposal;
- AI rationale is not a citation;
- AI-origin lexicon drafts require a reviewer-supplied source URL before approval;
- approved runtime knowledge must remain distinguishable from base/source data;
- any future corpus import must obey its license and attribution requirements.

## Pronunciation research

Keep three layers separate:

1. classroom convention — designed to make consonantal transliteration pronounceable;
2. broad consonantal reconstruction — uncertain phonetic values with alternatives;
3. period/lexeme-specific historical reconstruction — only when comparative/corpus evidence is attached.

Do not train a TTS model on classroom readings and market it as “how Ancient Egyptians actually sounded.”

## Corpus integration

Before importing any corpus/dictionary:

- check license and attribution;
- preserve stable source/lemma/text IDs;
- store the original corpus version;
- map, do not erase, alternate transliteration conventions;
- preserve morphological/syntactic annotations;
- keep English and Swahili target translations as sense-level data;
- document automated transformations;
- make the import reproducible.

## Security boundary

Reviewers can approve research corrections; administrators can export the approved dataset manifest. Dataset export and model training are separated intentionally. A compromised reviewer account should not be able to deploy a model.

For institutional deployment add MFA/SSO, immutable audit logging, PostgreSQL, shared rate limits and a model registry with deployment permissions independent from application-content permissions.
