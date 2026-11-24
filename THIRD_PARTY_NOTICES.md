# Third-party notices

## OpenAvatarChat

The live avatar chat (`app/avatar_chat/`, `app/static/js/avatar.js`) ports the architecture and parts of the code of
[OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat), Copyright HumanAIGC-Engineering,
licensed under the Apache License, Version 2.0.

Adapted portions, each modified as described in its module docstring:

| This project | Derived from (OpenAvatarChat) |
|---|---|
| `app/avatar_chat/text_tools.py` | `src/handlers/tts/token_buffer.py`, `src/engine_utils/text_filter.py` |
| `app/avatar_chat/session.py` (message names and payload fields) | `src/handlers/client/ws_client/ws_message_protocol.py` |
| `app/avatar_chat/brain.py` (layered prompt, streaming LLM) | `src/handlers/agent/prompt/prompt_compiler.py`, `src/handlers/llm/openai_compatible/` |
| `app/avatar_chat/visemes.py` (ARKit channel names) | `src/handlers/avatar/lam/assets/arkit_face_channels.txt` |

A copy of the Apache License 2.0 is available at https://www.apache.org/licenses/LICENSE-2.0.
No OpenAvatarChat model weights, avatar assets or frontend code are included.

## Noto fonts

`app/static/fonts/*.woff2` are subsets of Noto Sans Egyptian Hieroglyphs, Noto Sans Cuneiform, Noto Sans Ethiopic,
Noto Sans Old Italic and Noto Sans Old North Arabian, Copyright The Noto Project Authors, licensed under the
SIL Open Font License 1.1 (`app/static/fonts/OFL.txt`). They were taken from the Fontsource 5.2.6 packages.

`app/data/signs/glyph_metrics.json.gz` holds glyph bounding boxes measured from Noto Sans Egyptian Hieroglyphs (same licence); no outlines are copied.

## Unicode Unikemet

`app/data/signs/unikemet.json.gz` is derived from `Unikemet.txt` in the Unicode Character Database 18.0, Copyright © Unicode, Inc.,
used under the Unicode License v3 (https://www.unicode.org/license.txt).

## Thesaurus Linguae Aegyptiae

`app/data/corpus/tla_samples/*.json` are sample records from the Thesaurus Linguae Aegyptiae (Berlin-Brandenburg Academy of
Sciences and Humanities and Saxon Academy of Sciences in Leipzig), taken from the test resources of the tla-es and tla-web
projects, licensed CC BY-SA 4.0. Text and sentence translations in `app/data/eval/artifact_benchmark.json` marked `tla-draft`
come from the same source under the same licence.

## Comprehensive Coptic Lexicon

`app/data/coptic/ccl.json.gz` is derived from the Comprehensive Coptic Lexicon v1.2 (Freie Universität Berlin / BBAW,
doi:10.17169/refubium-2333), licensed CC BY-SA 4.0. The derived file is shared under the same licence.
