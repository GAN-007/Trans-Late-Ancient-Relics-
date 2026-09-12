# Security and privacy model

## Authentication

Passwords use Python's stdlib `scrypt` password KDF with a random salt. Sessions use random opaque tokens. Only a SHA-256 digest of each session token is stored in SQLite. The browser receives the token only in an HttpOnly, SameSite=Lax cookie.

Roles are `learner`, `contributor`, `reviewer`, and `admin`. Unauthenticated visitors are treated as guests.

## Camera

The camera is requested only after a user action. Frames are compressed in the browser and submitted to `/api/vision/analyze`. The application validates MIME type, file signature, base64 integrity and a 5 MB decoded size limit.

The application does not write submitted image bytes to disk or database. If an external AI provider is configured, the image is sent to that provider for inference; provider-side retention and policy are controlled by that provider/account configuration.

Live scan is not continuous video upload. The web client samples a still frame approximately every 2.6 seconds and avoids overlapping requests.

## Microphone

The app does not upload raw microphone audio to its FastAPI backend. Browser speech recognition produces a transcript; the transcript is then translated like typed text. Browser/platform implementations may use their own speech services, so users should consult their device/browser privacy settings.

## Translation history

History is opt-in and only available to authenticated users. Camera frames are never saved to history. A user can clear their history through the API.

## AI knowledge loop

AI-generated lexical proposals are never auto-approved. They remain pending until a reviewer or admin accepts them. This prevents self-reinforcing model errors from silently entering the teaching lexicon.

## HTTP security

The server adds CSP, frame denial, MIME-sniffing protection, restrictive referrer policy, COOP and a Permissions-Policy limiting camera/microphone to the same origin.

## Deployment notes

- Keep `OPENAI_API_KEY` and bootstrap passwords out of Git.
- Use HTTPS in production.
- Use a reverse proxy/API gateway for distributed rate limiting.
- Back up the runtime SQLite database if learner progress/review history matters.
- For multi-instance deployments, migrate runtime state to PostgreSQL and use a distributed scheduler/queue rather than the single-process background loop.
