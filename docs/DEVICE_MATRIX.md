# Device and Interaction Matrix

| Environment | Core text/ESHB | PWA | Camera | Speech recognition | Read aloud | Cloud vision |
|---|---|---|---|---|---|---|
| Modern Android Chrome | Full | Full | Full | Usually available | Full | Full when configured/authenticated |
| Modern iPhone/iPad Safari | Full | Installable web app | Full on HTTPS | Browser/version dependent | Full | Full when configured/authenticated |
| Desktop Chrome/Edge | Full | Full | Webcam if present | Usually available | Full | Full when configured/authenticated |
| Desktop Safari | Full | Partial/full by version | Webcam if present | Version dependent | Full | Full when configured/authenticated |
| Firefox desktop/mobile | Full | Varies | Camera supported | Web Speech Recognition often absent | Speech synthesis varies | Full when configured/authenticated |
| Offline | ESHB/static learning available | Cached shell | Preview possible | Device/browser dependent | Device dependent | No remote vision |

The UI tests for capability at runtime and disables or explains unavailable features. It does not infer that all browsers expose the same speech APIs.
