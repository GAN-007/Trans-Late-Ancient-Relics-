# Security, Identity and Permission Model

## Roles

| Capability | Guest | Learner | Contributor | Reviewer | Admin |
|---|---:|---:|---:|---:|---:|
| ESHB encode/decode | ✓ | ✓ | ✓ | ✓ | ✓ |
| Dictionary and lessons | ✓ | ✓ | ✓ | ✓ | ✓ |
| Deterministic translation | ✓ | ✓ | ✓ | ✓ | ✓ |
| Browser speech/read-aloud | ✓ | ✓ | ✓ | ✓ | ✓ |
| Start local camera preview | ✓ | ✓ | ✓ | ✓ | ✓ |
| Cloud vision when configured | — | ✓ | ✓ | ✓ | ✓ |
| Persist synchronized progress | — | ✓ | ✓ | ✓ | ✓ |
| Translation history | — | ✓ | ✓ | ✓ | ✓ |
| Submit translation feedback | ✓ | ✓ | ✓ | ✓ | ✓ |
| Propose dictionary entries | — | — | ✓ | ✓ | ✓ |
| Review/approve/reject entries | — | — | — | ✓ | ✓ |
| Run AI research proposal loop manually | — | — | — | ✓ | ✓ |
| Manage roles/disable users | — | — | — | — | ✓ |
| View audit log | — | — | — | — | ✓ |

Roles are hierarchical. A reviewer inherits contributor and learner capabilities; an administrator inherits all capabilities.

## Sessions

Passwords are PBKDF2-HMAC-SHA256 hashed with individual random salts. Session tokens are random, stored server-side only as SHA-256 hashes, and delivered in an HttpOnly SameSite=Lax cookie. Production HTTPS deployments should set `ESHB_SECURE_COOKIES=true`.

## Camera and microphone privacy

The app never requests camera or microphone access during page load. Permission is requested only after the user presses the relevant button. Camera frames are sent to the configured vision endpoint only when the user triggers analysis or enables auto-scan. The browser speech-recognition implementation may itself use a browser/vendor speech service depending on the browser; the app surfaces support rather than pretending recognition is entirely local.

## AI governance

External AI output is never inserted directly into the reviewed lexicon. The flow is:

`feedback/unresolved term → research candidate → pending proposal → human reviewer → approved community lexicon`

This prevents a self-reinforcing model error from becoming authoritative merely because it was generated repeatedly.

## Bootstrap administrator

Set both:

- `ESHB_ADMIN_EMAIL`
- `ESHB_ADMIN_PASSWORD`

The application creates the administrator on first startup if the email does not exist. If the account already exists, it is promoted to administrator. Store these values in a secret manager in production.

## Deployment hardening beyond this repository

For public internet scale add reverse-proxy TLS, request/body limits, provider-level quotas, distributed rate limiting, managed database backups, secrets management, central logs, SSO where required, vulnerability scanning and database encryption/host-disk encryption.
