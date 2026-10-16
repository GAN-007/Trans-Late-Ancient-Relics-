# Universal Translator — End-to-End Architecture, Research and Gap Assessment
**Audit date:** 2026-10-16  
**Reference:** https://github.com/Tencent-Hunyuan/Hy-MT2  
**Destination:** https://github.com/GAN-007/Trans-Late-Ancient-Relics-  
**Change branch:** feat/universal-neural-translation-20261016  

## Executive evaluation

Trans-Late Ancient Relics v3 has a valuable evidence-aware Ancient Egyptian research/teaching core. Tencent Hy-MT2 has a complementary specialized modern-language translation model family and training/evaluation ecosystem. They must not be conflated. A general translation LLM can assist research but is not a decipherment engine, sign-language recognizer, communications-signal demodulator, or authenticated Egyptian epigraphic source.

This enhancement preserves historical translation, ESHB, IPA, morphology, AI vision, WebSocket interaction, learning, authentication, human-reviewed research contributions and opt-in data governance. It adds a separately routed modern-language neural text service and an optional Cloud Translation gateway, a modern-language interface, structured text safeguards, subtitle support and reviewed bilingual data export.

**Claim boundary:** This change establishes a real, testable integration contract; it does not ship multi-gigabyte Tencent model weights, a paid Google Cloud credential, full Greek/Sumerian/Mayan decipherment, video sign-language translation, unknown-signal semantics or production training jobs. No network model inference works until a real model server or Cloud API key is configured.

## 1. Repository inventories and inspection scope

A full recursive tree listing was retrieved from GitHub for each repository, both non-truncated. Tencent: 56 tracked files / 65 entries. Destination before these changes: 76 tracked files / 87 entries. Key implementation files, training assets, documented API boundaries, configuration, tests, licenses and existing gap reports were read. This is a complete *repository path inventory* and a targeted implementation audit, not a claim to have executed or semantically examined every line of every file or trained any model locally.

### 1.1 Tencent Hy-MT2 path groups and responsibilities

| Path | Function and engineering observations |
|---|---|
| README.md, README_CN.md | Model catalogue, 33-language claim plus variants, recommended prompts, inference paths, quantization choices, reports and benchmark links |
| LICENSE.txt | Hy-MT2 software Apache License 2.0: attribution and notice obligations apply to copied software |
| LICENSE-IFMTBench.txt | IFMTBench *dataset* licensed CC BY 4.0, separate from code/model agreements |
| imgs/logo-en.png, imgs/logo-zh.png, imgs/main_result.png | Branding and reported benchmark visual; not inference implementation |
| train/README.md, train/README_CN.md | Supervised instruction data, GPU requirements, single/multi-node training and fine-tuning workflows |
| train/requirements.txt | Training-only PyTorch/Transformers/DeepSpeed/PEFT dependencies |
| train/data/example_data.jsonl | Instruction-following supervised learning examples |
| train/deepspeed_support/train.py | Large-model/MoE training entry, data preparation and trainer orchestration |
| train/deepspeed_support/train_dense.py | Dense-family supervised-fine-tuning entry |
| train/deepspeed_support/train.sh, train_dense.sh | Multi-configuration execution and distributed launcher scripts |
| train/deepspeed_support/train_lora.sh, train_dense_lora.sh | PEFT/LoRA training launchers |
| train/deepspeed_support/merge_lora_weight.py, merge_lora_weight.sh | Model adapter weight-merge tooling |
| train/deepspeed_support/ds_zero2_no_offload.json | ZeRO-2 sharding without CPU offload |
| train/deepspeed_support/ds_zero2_offload.json | ZeRO-2 with offload |
| train/deepspeed_support/ds_zero3_no_offload.json | ZeRO-3 sharding without CPU offload |
| train/deepspeed_support/ds_zero3_offload.json, ds_zero3_offload_no_auto.json | ZeRO-3 offload variants |
| train/llama_factory_support/hy_dense_1_8b_full_sft.yaml | 1.8B full supervised fine-tune configuration |
| train/llama_factory_support/hy_dense_1_8b_lora_sft.yaml | 1.8B LoRA configuration |
| train/llama_factory_support/hy_dense_7b_full_sft.yaml | 7B full SFT |
| train/llama_factory_support/hy_dense_7b_lora_sft.yaml | 7B LoRA |
| train/llama_factory_support/hy_v3_full_sft.yaml | Large-family full fine-tune |
| train/llama_factory_support/hy_v3_lora_sft.yaml | Large-family LoRA |
| train/llama_factory_support/ds_zero2_offload.json, ds_zero2_offload_lora.json, ds_zero3_offload.json | Training memory strategy templates |
| train/llama_factory_support/dataset_info.json | Training corpus registration |
| train/llama_factory_support/hy_dense_template.py, hy_v3_template.py | Model-specific conversation templates |
| train/llama_factory_support/hy_v3_patches.py | Model integration/compatibility hooks |
| train/llama_factory_support/train_hy_dense.py, train_hy_v3.py | LLaMA-Factory launching/patching utilities |
| train/llama_factory_support/train_lf.sh, train_lf_dense.sh | LLaMA-Factory training entrypoints |
| train/llama_factory_support/convert_zero_to_hf.sh | Checkpoint export/conversion |
| train/tools/check_converted.py | Converted checkpoint verification |
| train/tools/convert_ckpt_to_outer.py | Checkpoint-layout conversion |
| IFMTBench/README.md, README_zh.md | Instruction-following evaluation tasks and procedure |
| IFMTBench/config.py | Benchmark/evaluator setup |
| IFMTBench/run_eval.py | Evaluation runner |
| IFMTBench/eval/__init__.py, llm_judge.py | Evaluator package and model-based judge |
| IFMTBench/eval/rule_validators.py | Glossary, delimiter, structural-layout, and code-asset preservation checks |
| IFMTBench/eval/scoring.py | Evaluation scoring and aggregation |
| IFMTBench/requirements.txt | Evaluation dependencies |
| IFMTBench/data/sample_output.jsonl | Demonstration of expected evaluation output |
| IFMTBench/data/test_single_constraint.jsonl | Single-constraint benchmark test set |
| IFMTBench/data/test_multi_constraint.jsonl | Multi-constraint benchmark test set |

Tencent's GitHub repository is **primarily research, training, inference instructions and benchmarking**, not a turnkey camera/audio/sign-language application. Actual pretrained weights are distributed separately through Hugging Face/ModelScope. Training source code does not itself imply the datasets or end-to-end pretraining recipe used to originate the published checkpoint are released.

### 1.2 Destination repository modules and responsibilities

| Group | Tracked files and assessment |
|---|---|
| Server | app/main.py; FastAPI lifecycle, HTTP and websocket endpoints |
| Linguistic codec | app/eshb.py; strict reversible ESHB and phonetic bridge |
| Egyptian language | app/egyptian.py, app/epigraphy.py, app/morphology.py, app/translator.py; dictionaries, hieroglyphs, signs, templates, linguistic boundaries |
| Context/ranking | app/contextual.py, app/ai.py; context interpretation and optional model review |
| Vision | app/vision.py, app/vision_local.py; optional hosted/local inference and disagreement reporting |
| Speech/realtime | app/speech.py, app/streaming.py; pronunciation profiles and two websocket journeys |
| Knowledge | app/knowledge.py, app/learning_loop.py, app/active_learning.py; proposals, reviewer gates and dataset manifests |
| User features | app/auth.py, app/history.py, app/feedback.py, app/pedagogy.py; roles, lessons, progress, feedback |
| Data | app/data/lessons/01_foundation.json through 04_advanced.json; app/data/lexicon/01.json through 09.json; app/data/references.json |
| UI | app/static/index.html, styles.css, icon.svg, manifest.webmanifest, service-worker.js |
| JavaScript | app/static/js/account.js, api.js, app.js, camera.js, core.js, learn.js, lens.js, speech.js, talk.js, translate.js |
| Deployment | Dockerfile, docker-compose.yml, .dockerignore, .gitignore, Makefile, requirements.txt, requirements-vision.txt, pyproject.toml |
| Testing | tests/test_core.py, test_v2.py, test_v3.py; .github/workflows/ci.yml |
| Documentation | ARCHITECTURE.json, README.md, docs/CONFIGURATION.md, END_TO_END_AUDIT.md, SECURITY_PRIVACY.md, USER_JOURNEYS.md, V3_GAP_AUDIT.md, V3_RESEARCH_MODEL_GOVERNANCE.md, models/README.md and model class-map example |
| CLI/license | cli.py and LICENSE |

**Observed design strength:** The historical Egyptian/ESHB distinction, multi-role review process, generated review datasets, and non-fabrication principle are unusual and worth preserving.

**Observed weakness:** The modern general multilingual scope, an accurate supported-language/provider registry, a discrete neural translation service, structured-message preservation and subtitle localization were absent before this branch. More advanced gaps such as trained sign recognition or historical corpora were already acknowledged in the repo's own v3 documentation.

## 2. Tencent ML architecture and train/infer logic

### 2.1 Model families
- **1.8B dense**: lower resource inference, optional aggressive quantization. An on-device 1.25-bit release is reported near 440 MB; it is a model artifact/storage claim, not a promise about runtime RAM or CPU compatibility.
- **7B dense**: larger model capacity, correspondingly higher memory and serving requirements.
- **30B-A3B MoE**: mixture-of-experts variant with a relatively lower active parameter count than total parameters; deployment and quantization are architecture-sensitive.
- **Fast-thinking translation**: instruction following specialized for cross-language rendering, domain terminology, formatting and contextual intent.
- **Coverage**: Tencent describes 33 languages and additional varieties. See the live upstream catalogue; this repository's adapter enumerates explicitly documented names/codes rather than promising unrestricted translation.

### 2.2 Inference
1. Client creates a task instruction: source/target language names, style, terminology and content.
2. Tokenizer builds a chat-style input with the expected template; the model has no default system prompt in Tencent documentation.
3. Model inference generates text, not annotated glyphs/audio/video.
4. Optional runtime backends include Hugging Face Transformers, vLLM, SGLang and llama.cpp/GGUF (including format-specific kernel constraints).
5. Outputs should undergo deterministic checks: terminological matches, formatting, variable preservation and evaluation.

Documented dense inference parameters include temperature 0.7, top_p 0.6, top_k 20, repetition penalty 1.05, and max_tokens 4096. 30B-A3B recommends a different top_p/repetition setting. This integration exposes conservative OpenAI-compatible chat-completions parameters and leaves full backend-specific performance tuning to the serving stack. The reference's 8192 context length requires token-aware segmentation for longer texts.

### 2.3 Training
- Input format: JSONL with a user instruction and assistant reference translation.
- Training: supervised fine-tuning (SFT), full parameter and LoRA/PEFT, Transformers Trainer / DeepSpeed or LLaMA-Factory.
- Distributed support: ZeRO-2, ZeRO-3, CPU/offload configurations, multiple GPUs/nodes.
- Outputs: checkpoints, optional adapter merge, export/conversion and comparison against held-out evaluation.
- Tencent lists minimum configuration estimates at context 8192: 1.8B 24 GB-class GPU; 7B LoRA 80 GB and full fine-tune 2 x 80 GB; 30B-A3B LoRA/full fine-tune configurations around 8 x 80 GB. These are guidance figures from upstream, not verified benchmarks from this deployment.
- Critical missing product work: source rights checks, data validation, deduplication, train/validation leakage prevention, benchmark provenance, deployment approval, observability, drift and reversal procedures. We introduce the data-export foundation but not an unsupervised weight-update mechanism.

### 2.4 Evaluation
IFMTBench makes an important design choice: evaluate *instruction compliance*, not only perceived fluency. Coverage includes terminology, delimiters, placeholders, structured JSON/HTML/CSV/Markdown and constraint combinations. Automated validators are useful but not substitutes for bilingual expert assessment of meaning, register, tone or cultural acceptability. Do not copy datasets into the destination without CC BY attribution and proper dataset notices.

Suggested measurable gates:
- COMET/chrF/BLEU (paired with human linguistic adjudication);
- chrF and targeted morphology/diacritics for low-resource language variants;
- glossary term compliance (exact target term);
- protected placeholder preservation 100%;
- SRT cue count/timestamp invariance 100%;
- JSON key/value type invariance 100%;
- hallucination, omissions, protected entities, contextual ambiguity and reversibility tests;
- P50/P95 latency, memory, throughput and cost per million characters;
- calibration and escalation for obscure/historical scripts;
- fairness across languages and dialects, not only high-resource English pairs.

## 3. Google Translate research and actual attainable parity

Google officially stated in 2026 that Translate supports about **250 languages** and is used by over **one billion people monthly**. Its capabilities include direct text translation, handwriting and camera-photo translation, document and website workflows, conversation audio and a language practice ecosystem. A 2025 announcement describes live conversation support in 70+ languages. In 2026 Google described richer context/alternative translations and mobile live-translation improvements.

Official references:
- https://blog.google/products-and-platforms/products/translate/fun-facts-google-translate-20-years/
- https://blog.google/products-and-platforms/products/translate/google-translate-new-languages-2024/
- https://blog.google/products-and-platforms/products/translate/language-learning-live-translate/
- https://blog.google/products-and-platforms/products/translate/translation-context-ai-update/
- https://blog.google/products-and-platforms/products/translate/google-translate-ios-android-upgrades/
- https://support.google.com/translate/answer/6142483
- https://support.google.com/translate/answer/2534559
- https://docs.cloud.google.com/translate/docs/languages

**Crucial API distinction:** The consumer Google Translate website/app is not the Google Cloud Translation API. This branch uses the documented Google Cloud Translation Basic v2 API, which requires separate enabled Google Cloud credentials/billing, has its own model/service/language support, and does not automatically grant consumer-app camera, offline, conversation or handwriting features.

**Competitive parity sequence:** multilingual text → context/glossary/structured text → subtitle and document parsing → language detection → camera OCR and text overlays → voice ASR → neural MT → TTS with diarization and low-latency streams → personal phrasebooks/offline edge models → accessibility and sign-specific video understanding. Each is a separate shipped/tested product capability, not one translation-model checkbox.

## 4. Proposed production architecture

~~~text
Web / mobile / desktop / SDK / museum workstation
  |-- Contextual Egyptian translator (existing)
  |-- Multilingual text + glossary + JSON + SRT (this branch)
  |-- Camera, voice and researcher workflows (existing)
  v
FastAPI security, validation, rate limiting and authenticated workflows
  |-- ESHB reversible codec ──────────────────────────────── unchanged
  |-- Egyptian epigraphy, transliteration, morphology ────── unchanged
  |-- Vision local/AI, reviewer evidence gateway ─────────── unchanged
  |-- Universal MT router ─────────────────────────────────── new
  |      |-- Hy-MT2 API (operator-owned vLLM/SGLang/etc.)
  |      |-- Google Cloud Translation Basic v2 (optional)
  |      |-- source/target capability rules
  |      |-- placeholders/glossary/structured JSON/SRT checks
  |      '-- explicit provider + model + no-historical-proof status
  '-- Human-approved bilingual dataset exporter ─────────── new
             |-- legal/provenance review
             |-- document-grouped train/validation split
             |-- train.jsonl + validation.jsonl + manifest
             '-- future offline LoRA training/registry/evaluation gate

Future modality workers:
  OCR/script classifier, ASR, speaker diarization,
  sign-language pose/video segmentation, sign-to-gloss,
  acoustic/music/signal demodulation, TEI/EpiDoc, corpus search
  -> uncertainty-aware language/evidence router
~~~

**Server secrets:** Cloud translation key and model-server API key stay server-side. No public endpoint accepts an arbitrary inference-server URL. Provider errors are summarized without returning raw keys or remote response bodies. Output is rendered using textContent, not HTML.

## 5. Implemented in this enhancement branch

| File | Status | Purpose |
|---|---|---|
| app/universal_translation.py | Implemented | Language aliases, modern-language boundary, explicit/automatic provider routing, Hy-MT2 chat completions and optional Cloud Translation, URL placeholder masking, terminology integrity checks, JSON and SRT workflows |
| app/main.py | Extended | New capabilities and /api/universal/capabilities and /api/universal/translate endpoints; existing endpoints retained |
| app/static/index.html | Extended | Modern-language translation form next to original Egyptian translation journey |
| app/static/js/universal.js | New | Provider status, translation, safe DOM rendering, copy result |
| app/static/js/app.js | Extended | Initializes new workflow |
| scripts/build_mt_dataset.py | New | Approved bilingual CSV → Hy-MT2-compatible SFT JSONL and provenance manifest |
| tests/test_universal_translation.py | New | Route contract, rejection paths, glossary/placeholder integrity, JSON/SRT invariants, original Egyptian API |
| tests/test_mt_dataset.py | New | Review/export/license filtering and split/duplicate handling |
| docs/UNIVERSAL_TRANSLATOR_AUDIT_2026.md | New | This assessment |

**Existing unchanged features:** historical hieroglyphic rendering, Egyptian morphological analysis, ESHB and IPA encoders, lessons/lexicon, user roles, WebSockets and existing governance.

## 6. Example journeys

**Modern bilingual traveller:** Enter French target, English source, choose automatic route. With Hy-MT2 served, translate; return provider, model and content. No historical claims.

**Kenyan Kiswahili learner:** English → Swahili. Hy-MT2 does not document Swahili, so auto mode must select Google Cloud if configured; otherwise explicit failure, not invented output. The Ancient Egyptian English/Swahili lexicon remains distinct.

**Website localization engineer:** Submit JSON. Translate text-bearing keys such as title, label, body, placeholder, caption and content. Preserve IDs, numerical values, arrays, nested objects, keys and masked variables/tags. Explicit extra translatable keys can be supplied. Output JSON formatting may be normalized; semantic structure is preserved.

**Video subtitler:** Submit SRT. Preserve cue identifiers/timing; translate dialogue and reject invalid cues. This is subtitle *text* translation, not automatic audiovisual speech transcription, speaker attribution or lip syncing.

**Archaeologist:** Use existing vision/sign-analysis/research evidence tools, not blind Hy-MT2 for a hieroglyph. Preserve period/provenance and scholarly uncertainty.

**Museum contributor:** Human reviews a modern bilingual pair and confirms license, provenance and author. Dataset tool exports it for offline SFT; no production model changes are automated.

**Accessibility user:** Existing browser speech recognition and text-to-speech capabilities remain; unifying them with the general modern-language model across devices requires further integration and language-specific QA.

## 7. Gap matrix: missing and partially realized niches

| Priority | Domain | Status | Required engineering and research |
|---|---|---|---|
| P0 | Text model serving | Integration only | Launch and harden production Hy-MT2 GPU/CPU endpoint; model downloads, capacity tests, licensing notices |
| P0 | Google Cloud broader-language access | Integration only | Enable Cloud Translation API, secure billing/keys, retrieve supported-language list, cost & quota controls |
| P0 | Neural MT accuracy | Not demonstrated | Real parallel corpora, domain metrics, expert reviews, latency and robustness |
| P0 | Privacy and abuse | Partial | Distributed rate limits, credential rotation, audit logging, consent boundaries, egress restrictions |
| P1 | Language identification | Cloud auto optional | Explicit detector for Hy-MT2 routing; prevent false positives on rare/historical scripts |
| P1 | Token/length segmentation | Partial | Token-count aware segmentation, context overlap, batching, document cross-chunk coherence |
| P1 | Structured files | Partial | DOCX/PDF/PPTX/XLSX, HTML DOM, Markdown AST, PO/XLIFF, resource bundle localization |
| P1 | Speech-to-speech | Browser speech tools only | Robust multi-language ASR, VAD, streaming MT, TTS, diarization, interruption/crosstalk, translations with latency budget |
| P1 | Camera document OCR | Optional current model paths | Script-specific OCR, geometry, layout, multi-line reading, overlay coordinate restoration |
| P1 | Historical corpora | Research limited | Licensed photographed artifacts, citations, chronological provenance, expert-reviewed morphology and syntax |
| P1 | Sign-language translation | Not implemented | ASL/BSL/KSL and other distinct signed languages require separate datasets, lexical grammar, video pose/hands/face nonmanual cues, temporal models and Deaf-community evaluations |
| P1 | Heritage and endangered languages | Limited | Community-controlled corpora, informed consent, dialect variation, morphology, coverage reporting |
| P2 | Handwriting | Not generalized | Handwriting OCR by script/time period, uncertainty and author variation |
| P2 | Animal/acoustic signals | Not implemented | Identify acoustic events; semantic 'translation' only if grounded communication codebook exists |
| P2 | Radio/wave protocols | Not implemented | Signal sampling, demodulation, error correction, protocol identification, source authorization; unknown transmissions cannot be treated as natural-language speech |
| P2 | Braille, Morse, tactile & AAC | Not generalized | Codebooks, accessible input/output adapters, modality-specific validation |
| P2 | Inscriptions beyond Egypt | Not implemented | Sumerian cuneiform, Mayan glyphs, Linear B etc. need separate attested corpora; undeciphered scripts cannot be truthfully 'translated' by a generic LLM |
| P2 | Offline mobile | Not implemented | Small quantized models, STQ/llama.cpp compatibility, caching, app packaging and performance QA |
| P2 | Production observability | Not implemented | Versioned model registry, traces, per-language quality, cost, rollback, abuse and uptime SLOs |
| P2 | Experiments and training platform | Dataset export only | DVC/MLflow, scheduled LoRA, multi-GPU training, evaluation gates, canary, rollback |
| P3 | Advanced museum AR | Not implemented | 3-D object registration, multi-frame glyph localization, scholar-reviewed overlays |
| P3 | Cross-cultural knowledge graph | Not implemented | Ontology, aligned interlinear gloss, attestation graph, curator review and query API |

### Commercial and public-interest niches

Museums/archaeology; heritage preservation; tourism/field visits; classroom and self-learning; immigrant community assistance; global customer support; localization pipelines; subtitling; captions/accessibility; medical interpreters with human safeguards; legal translation with reviewer workflows; endangered-language documentation; research paleography; historical lexicography; OCR of archival manuscripts; government multilingual communication; disaster communication; real-time conference translation; off-grid expeditions; audiovisual/performing-arts localization; signed-language accessibility with consent, Deaf-led evaluation and dedicated sign-language research.

Each niche has domain validation and legal/safety requirements; one model cannot be marketed as independently competent in every domain or all signed languages.

## 8. Safe deployment and API instructions

### Hy-MT2 model serving

Provision a suitable model host separately. Consult current upstream vLLM, Transformers and specific Hy-MT2 quantization compatibility. Example for a compatible operator-owned local server:

~~~bash
# In an environment with a compatible vLLM build and sufficient model memory:
vllm serve tencent/Hy-MT2-1.8B --host 127.0.0.1 --port 8001
# In the FastAPI application's process environment:
export UNIVERSAL_MT_BASE_URL=http://127.0.0.1:8001/v1
export UNIVERSAL_MT_MODEL=tencent/Hy-MT2-1.8B
uvicorn app.main:app --reload
~~~

These are invocation examples, **not evidence of a successful local model start**. Actual model artifact download, hardware capacity and backend-specific compatibility are still needed.

### Optional Cloud Translation

~~~bash
# Enable Google Cloud Translation API and corresponding billing/restrictions first.
export GOOGLE_CLOUD_TRANSLATE_API_KEY="REPLACE_WITH_REAL_SECRET"
# The key is intentionally absent from Git and never sent to the browser.
~~~

Cloud Translation supports more modern languages than Hy-MT2 in its own catalogue, but not ancient scripts, unknown waves or signed-language video by implication.

### Modern text API

~~~http
POST /api/universal/translate
Content-Type: application/json

{
  "text": "Welcome to the museum, {{visitor}}!",
  "source_language": "en",
  "target_language": "fr",
  "provider": "auto",
  "format": "text",
  "style": "formal",
  "context": "museum visitor signage",
  "glossary": {"museum": "musée"}
}
~~~

### Structured JSON API

~~~json
{
  "text": "{\"id\":\"museum.hello\",\"title\":\"Welcome\",\"count\":17}",
  "source_language": "en",
  "target_language": "fr",
  "format": "json",
  "translatable_keys": ["title"],
  "provider": "auto"
}
~~~

### Human-approved training data export

~~~bash
python scripts/build_mt_dataset.py approved_parallel_corpus.csv training_output --validation-percent 10
# Output:
# training_output/train.jsonl
# training_output/validation.jsonl
# training_output/manifest.json
~~~

The input must include columns source_text, target_text, source_language, target_language, document_id, license, evidence_url, approved, approved_by. Restricted or third-party data requires explicit rights and compliance review. Tensor checkpoints are deliberately excluded from Git.

## 9. Quality gates for merging

- Python compileall on app, cli.py and scripts.
- Pytest existing core/v2/v3 and new modern translation/dataset suites on Python 3.11, 3.12 and 3.13.
- Browser JavaScript syntax checks.
- Docker image build.
- No provider-required live network calls in deterministic test suite.
- No unsupported universal/sign/ancient-language capability claims.
- Inspect PR status checks before merging.

**Known verification limit:** Mock-based tests confirm request/response shape and safety invariants, not real neural translation accuracy. A real model host, benchmark dataset, and end-to-end multilingual corpus tests must be separately provisioned before stating production completeness.

## 10. Reference material and licensing

- Tencent source: https://github.com/Tencent-Hunyuan/Hy-MT2
- Tencent model weights: https://huggingface.co/collections/tencent/hy-mt2
- Tencent training guide: https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/train/README.md
- Tencent instruction benchmark: https://github.com/Tencent-Hunyuan/Hy-MT2/tree/main/IFMTBench
- Tencent software license: https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/LICENSE.txt
- Tencent benchmark dataset license: https://github.com/Tencent-Hunyuan/Hy-MT2/blob/main/LICENSE-IFMTBench.txt
- Google Cloud supported language service: https://docs.cloud.google.com/translate/docs/languages
- Google consumer product documentation: https://support.google.com/translate
- Existing source repository: https://github.com/GAN-007/Trans-Late-Ancient-Relics-

**No Tencent copyrighted training scripts, weights, dataset samples or IFMTBench corpus were copied in this enhancement**; its documented interfaces and architectural lessons informed original adaptation code. Reuse of future upstream assets must preserve the appropriate Apache/CC BY license attribution.
