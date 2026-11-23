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

Client → server: `InitializeAvatarSession {persona, language, context}`, `SendHumanText {stream_key, mode: increment|full_text, text, end_of_speech}`, `SendHumanImage {image (data URL), text, source: upload|camera|live}`, `Interrupt`, `TriggerHeartbeat`, `EndSpeech {stream_key}`, `UpdateContext {...}`, `SetPersona {persona, language}`, `SetLanguage {language}`.

Server → client: `AvatarSessionInitialized` (includes `vision` availability and `languages`), `EchoHumanText` (with `attachment` for images), `EchoAvatarText` (streamed increments), `AvatarSpeech {text, voice, motion, segment, end_of_speech}`, `AvatarReading {reading}`, `AvatarCard` (verified translation table), `AvatarLiveStatus` (busy / throttled / unchanged), `LanguageChanged`, `AvatarNotice`, `ChatSignal` (stream_begin / stream_end / stream_cancel), `InterruptAccepted`, `InterruptNotification`, `AvatarHeartbeat`, `Error {code, message}`.

`AvatarSpeech.motion` is `{channels, fps, duration, frames: [{t, v, w}]}`, where `w` holds ARKit blendshape weights such as `jawOpen`, `mouthFunnel` and `mouthPucker`. A renderer for a 3D or Gaussian-splat head can consume the same frames.

## Reading what you show it, like a teacher with a book

Show the guide writing in any of three ways:

- **Camera**: press *Camera* and then *Read what I see*, or just ask "what does this say?" while the camera is on.
- **Live reading**: the browser compares tiny frames and sends one only when the view has changed and then held still for a moment. The guide reads new text as it comes into view, never interrupts itself, and stays quiet when the scene hasn't changed.
- **A photo or pasted text**: attach, paste or drop a photo, or paste hieroglyphs, cuneiform, Ge'ez fidel, Old Italic, Safaitic or Arabic letters straight into the chat. Pasted text is read fully offline.

Every reading is taught the same way, in the learner's chosen language (English or Kiswahili):

1. What the script and language are, and which way to read. On a wall, the direction comes from the way the signs face.
2. The whole meaning.
3. Word by word: how to say it (Egyptological convention: *nfr* → "nefer", *ꜥnḫ* → "ankh"), what it means, and what each sign does (sound sign, word sign, helper sign, or a meaning marker you don't say aloud).

The reading card highlights each word as the guide reads it, and a word board on the stage holds up the current word. Tap any word to hear it explained again.

**Tutor mode.** Say *quiz me* (*nijaribu*). The guide points at each word, asks you to say it and then what it means, accepts close answers (speech recognition mishears ancient words), gives a hint and then the answer, and keeps score. The card hides its answers until the quiz ends. *Read it again*, *word 3*, *slower* / *faster* and *stop* (*soma tena*, *neno la 3*, *polepole*, *acha*) work at any time.

**How readings are checked.** Pasted and detected signs are read from deterministic data: Unicode sign names, the Gardiner sign catalog, the Middle Egyptian lexicon and the ancient-language ladder (which also parses whole sentences). A vision model's reading of a photo is compared word by word with the same data, and each word is marked *confirmed*, *disputed* or *read from photo*. The guide says aloud when something is only likely. With the on-device sign detector and a vision model both available, disagreements are pointed out.

| Needs | Pasted text | Photo / camera |
|---|---|---|
| Nothing configured | Works | Explains it can't see yet |
| On-device ONNX sign detector | Works | Reads detected hieroglyphs |
| Vision model (`OPENAI_API_KEY`) | Works | Reads any script, checked against the data above |

## The guide's answers

Every turn first runs grounding tools:

- *translate*: "How do you say X in Sumerian", "translate X into every language", "Tafsiri X kwa Kilatini"
- *meaning*: "What does lugal mean", "Maana ya lugal ni nini"
- *languages*: "Which languages do you know", "Unajua lugha gani"

Tool results go into the prompt's environment layer so the model repeats verified forms instead of inventing them, and a card with every script appears in the chat. Without a model, the guide answers from these tools directly and says plainly that open conversation needs a model.

Personas: **Nefer** (scribe), **Amani** (teacher) and **Theo** (historical linguist). Each has its own voice, pitch and look and can speak English or Kiswahili. The learner's language choice is kept when switching guides.

## Speed

- Speech starts on the first finished sentence; a photo turn starts with a spoken "let me take a close look" while the image is read.
- Photos and frames are resized in the browser to at most 1280 px JPEG before upload.
- Translation and reading indexes are built in a background thread at startup (`ESHB_WARMUP`). The first reading then takes under a millisecond instead of about a second.
- Ancient-script fonts (Noto, OFL) are bundled and downloaded only when that script appears on screen, then cached for offline use.

## Configuration

Open conversation uses the existing `OPENAI_API_KEY`. To use a local or other OpenAI-compatible model, as OpenAvatarChat does:

```bash
export ESHB_AVATAR_LLM_API=chat_completions
export ESHB_AVATAR_LLM_BASE_URL=http://localhost:11434/v1   # Ollama
export ESHB_AVATAR_LLM_MODEL=llama3.1
```

The other limits are listed in [CONFIGURATION.md](CONFIGURATION.md).

## Privacy

Audio never leaves the browser. Only recognized text is sent. Photos and camera frames are analyzed in memory and not stored. Conversations live in server memory for the length of the session and are not stored.

## Limits

- Voice quality and available languages depend on the browser and operating system (Chrome and Edge have the broadest speech recognition; Swahili recognition and voices are not on every device). Without speech recognition, typing still works; without a voice, the face lip-syncs to subtitles.
- Lip-sync is derived from text, not audio, so it is approximate compared with OpenAvatarChat's LAM model.
- A photoreal avatar (LiteAvatar, MuseTalk, FlashHead) needs OpenAvatarChat's GPU server. Because the message names match, a client written for this protocol can be pointed at either.
