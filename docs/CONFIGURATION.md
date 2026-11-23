# Configuration

All secrets are server-side environment variables. The browser never receives API keys.

| Variable | Default | Purpose |
|---|---|---|
| `ESHB_ENV` | development | deployment mode |
| `ESHB_RUNTIME_DIR` | `data-runtime` | runtime SQLite/data directory |
| `ESHB_DB_PATH` | `<runtime>/eshb.sqlite3` | exact SQLite path override |
| `ESHB_SECURE_COOKIES` | production-dependent | mark auth cookie Secure |
| `ESHB_AI_PROVIDER` | openai if key exists, otherwise disabled | optional AI adapter |
| `OPENAI_API_KEY` | empty | server-side provider secret |
| `ESHB_AI_BASE_URL` | `https://api.openai.com/v1` | Responses-compatible API base |
| `ESHB_AI_MODEL` | `gpt-5.6` | text+vision model |
| `ESHB_AI_TIMEOUT_SECONDS` | 60 | provider request timeout |
| `ESHB_KNOWLEDGE_LOOP_ENABLED` | false | daily unresolved-term draft loop |
| `ESHB_KNOWLEDGE_LOOP_HOURS` | 24 | due interval |
| `ESHB_KNOWLEDGE_LOOP_BATCH` | 5 | max unresolved terms per cycle |
| `ESHB_BOOTSTRAP_ADMIN_USERNAME` | empty | optional first admin username |
| `ESHB_BOOTSTRAP_ADMIN_PASSWORD` | empty | optional first admin password |
| `ESHB_BOOTSTRAP_ADMIN_DISPLAY_NAME` | Administrator | display name |
| `ESHB_AVATAR_LLM_API` | `responses` | live chat model API: `responses` or `chat_completions` (OpenAI-compatible: Ollama, DashScope, vLLM…) |
| `ESHB_AVATAR_LLM_BASE_URL` | `ESHB_AI_BASE_URL` | live chat model endpoint; `http://localhost…` needs no key |
| `ESHB_AVATAR_LLM_MODEL` | `ESHB_AI_MODEL` | live chat model |
| `ESHB_AVATAR_LLM_API_KEY` | `OPENAI_API_KEY` | live chat model key |
| `ESHB_AVATAR_LLM_TIMEOUT_SECONDS` | 45 | live chat model read timeout |
| `ESHB_AVATAR_MAX_SESSIONS` | 20 | concurrent live chats per process |
| `ESHB_AVATAR_TURNS_PER_MINUTE` | 30 | messages per minute per chat |
| `ESHB_AVATAR_HEARTBEAT_TIMEOUT` | 30 | seconds without a heartbeat before a chat closes |
| `ESHB_AVATAR_CONNECTION_TTL` | 900 | maximum chat length in seconds |
| `ESHB_AVATAR_HISTORY_TURNS` | 20 | dialogue turns kept in memory for the model |

## Production

Use HTTPS. Set:

```bash
ESHB_ENV=production
ESHB_SECURE_COOKIES=true
```

Put the application behind a reverse proxy or managed ingress with TLS, request-size controls, access logs and infrastructure-level rate limiting. The app includes a small in-memory abuse guard, but a distributed deployment should enforce limits outside the process as well.
