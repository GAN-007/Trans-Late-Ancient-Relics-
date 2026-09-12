# AI, Live Camera and Conversation Architecture

## Design rule

The deterministic language engine remains useful without an AI account. AI is a second-pass reasoner and vision provider, not the sole source of truth.

## Text AI contract

Configure:

- `ESHB_AI_ENDPOINT`
- `ESHB_AI_API_KEY` (optional if the gateway uses another authentication method)

The app sends a JSON object containing the source text, source/target language, user-supplied context, intended speech act, translation mode and deterministic linguistic analysis. The external service should return a JSON object containing alternatives, rationale, confidence and uncertainties.

The endpoint is vendor-neutral so a deployment can front any model with its own gateway and logging/privacy policy.

## Vision AI contract

Configure:

- `ESHB_VISION_ENDPOINT`
- `ESHB_VISION_API_KEY`

A camera frame is sent as a base64 image data URL only when analysis is active. The requested contract includes:

- reading direction;
- sign candidates with optional Gardiner IDs and bounding boxes;
- transliteration candidates;
- translation candidates;
- uncertainty notes;
- free-form analysis notes.

If the endpoint is absent, camera preview still works, but the API returns `vision_provider_not_configured`. This is intentional: no fabricated OCR result is shown.

## Live camera journey

1. User opens Live Lens.
2. User presses Start camera.
3. Browser asks permission.
4. Video stays on-device until Analyze frame or Auto scan is enabled.
5. Canvas downsizes the current frame and encodes JPEG.
6. Backend validates the data URL and maximum size.
7. If cloud vision is configured, a signed-in user frame is sent to the configured gateway.
8. Response returns sign/transliteration/translation candidates and uncertainty.
9. UI shows the current analysis stream.

## Speech journey

1. User chooses English or Swahili recognition.
2. User presses Start microphone.
3. Browser/device speech recognition produces transcript where supported.
4. Transcript enters the same context-aware translation pipeline used by typed text.
5. Result can be read aloud with browser speech synthesis.
6. If the output is Egyptian transliteration, the app first converts it to a conventional Egyptological classroom reading and explicitly warns that the vowels are not historically certain.

## Knowledge-growth loop

Every unsupported token is counted with its source language and latest context. Translation feedback is stored separately. Reviewers can inspect these signals and manually run the AI proposal process.

Optional scheduled research is enabled with:

```text
ESHB_AUTO_RESEARCH_ENABLED=true
ESHB_AUTO_RESEARCH_INTERVAL_HOURS=24
ESHB_AUTO_RESEARCH_MIN_FREQUENCY=3
```

The scheduled loop produces **pending** lexical proposals only. Human approval remains mandatory.
