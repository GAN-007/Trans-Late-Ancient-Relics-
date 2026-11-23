# Live Avatar Chat

The **Live Chat** tab lets you talk, by voice or text, to an animated guide who answers in English or Swahili and translates into the ancient languages of the [Ancient Language Ladder](ANCIENT_LANGUAGE_LADDER.md). The design ports [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat) (Apache-2.0) into this app; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## How it maps to OpenAvatarChat

OpenAvatarChat chains handlers (VAD → ASR → LLM → TTS → Avatar) on GPU servers. Here, the parts that need GPU models run in the browser, and the server keeps the conversation logic.

| OpenAvatarChat stage | Here | Where |
|---|---|---|
| Client handler, WebSocket session protocol | Same message names and payloads (text and control subset) | `app/avatar_chat/session.py`, `/ws/avatar` |
| Silero VAD + SenseVoice ASR | Browser speech recognition (continuous, interim results) | `app/static/js/avatar.js` |
| LLM handler / Chat Agent (4-layer prompt) | Streaming OpenAI Responses or any OpenAI-compatible Chat Completions endpoint, grounded by ladder tools; offline responder when no model is set | `app/avatar_chat/brain.py` |
| TTS token buffer + text filter | Sentence buffering and markdown stripping (extended to ancient scripts) | `app/avatar_chat/text_tools.py` |
| TTS (CosyVoice / Edge TTS) | Browser speech synthesis, one sentence at a time | `avatar.js` |
| LAM audio→ARKit blendshapes, rendered by the client | Text→viseme→ARKit-channel motion track, re-timed to the real voice's word boundaries; SVG face | `app/avatar_chat/visemes.py`, `avatar.js` |
| StreamManager cancel chain + InterruptHandler | Reply streams are children of the human turn; Interrupt or a new turn cancels them; cancelled replies are not remembered | `session.py` |
| Duplex VAD barge-in | Speaking three or more words over the guide interrupts it (toggle) | `avatar.js` |
| Heartbeat, connection TTL, concurrent-session limit | Same (30 s, 900 s, configurable limit) | `session.py` |

## Protocol

Every frame is JSON: `{"header": {"name", "request_id"}, "payload": {...}}`.

Client → server: `InitializeAvatarSession {persona, context}`, `SendHumanText {stream_key, mode: increment|full_text, text, end_of_speech}`, `Interrupt`, `TriggerHeartbeat`, `EndSpeech {stream_key}`, `UpdateContext {...}`, `SetPersona {persona}`.

Server → client: `AvatarSessionInitialized`, `EchoHumanText`, `EchoAvatarText` (streamed increments), `AvatarSpeech {text, voice, motion, end_of_speech}`, `AvatarCard` (verified translation table), `AvatarNotice`, `ChatSignal` (stream_begin / stream_end / stream_cancel), `InterruptAccepted`, `InterruptNotification`, `AvatarHeartbeat`, `Error {code, message}`.

`AvatarSpeech.motion` is `{channels, fps, duration, frames: [{t, v, w}]}`, where `w` holds ARKit blendshape weights such as `jawOpen`, `mouthFunnel` and `mouthPucker`. A renderer for a 3D or Gaussian-splat head can consume the same frames.

## The guide's answers

Every turn first runs grounding tools:

- *translate*: "How do you say X in Sumerian", "translate X into every language", "Tafsiri X kwa Kilatini"
- *meaning*: "What does lugal mean", "Maana ya lugal ni nini"
- *languages*: "Which languages do you know", "Unajua lugha gani"

Tool results go into the prompt's environment layer so the model repeats verified forms instead of inventing them, and a card with every script appears in the chat. Without a model, the guide answers from these tools directly and says plainly that open conversation needs a model.

Personas: **Nefer** (English, scribe), **Amani** (Swahili teacher) and **Theo** (English, historical linguist). Each has its own voice language, rate, pitch and look.

## Configuration

Open conversation uses the existing `OPENAI_API_KEY`. To use a local or other OpenAI-compatible model, as OpenAvatarChat does:

```bash
export ESHB_AVATAR_LLM_API=chat_completions
export ESHB_AVATAR_LLM_BASE_URL=http://localhost:11434/v1   # Ollama
export ESHB_AVATAR_LLM_MODEL=llama3.1
```

The other limits are listed in [CONFIGURATION.md](CONFIGURATION.md).

## Privacy

Audio never leaves the browser. Only recognized text is sent. Conversations live in server memory for the length of the session and are not stored.

## Limits

- Voice quality and available languages depend on the browser and operating system (Chrome and Edge have the broadest speech recognition; Swahili recognition and voices are not on every device). Without speech recognition, typing still works; without a voice, the face lip-syncs to subtitles.
- Lip-sync is derived from text, not audio, so it is approximate compared with OpenAvatarChat's LAM model.
- A photoreal avatar (LiteAvatar, MuseTalk, FlashHead) needs OpenAvatarChat's GPU server. Because the message names match, a client written for this protocol can be pointed at either.
