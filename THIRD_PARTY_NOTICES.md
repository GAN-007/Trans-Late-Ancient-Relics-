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
