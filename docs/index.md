# AI Warp Tool

Ollama-compatible proxy on `:11435` for local + cloud model routing.

```
Client -> :11435 -> OllamaProvider -> localhost:11434 (no auth)
                                   -> cloud URL (Bearer token)
```

- [API Reference](api.md) — endpoints, routing rules, error codes
- [Package](package.md) — `src/onanana/` modules
- [Usage](usage.md) — setup, config, examples

## Prerequisites

- **Local** — [Ollama](https://ollama.com) must be installed and running on the target host (default `http://localhost:11434`)
- **Cloud** — one or more API keys saved in `secrets/keys.txt` (one per line, see [`secrets/keys.txt.example`](../secrets/keys.txt.example))

## Quick start

```bash
pip install -r requirements/requirements-dev.txt
python -m uvicorn apis.main:app --host 0.0.0.0 --port 11435
```

## Config

All `WARP_*` env vars are read from `secrets/.env` or the environment:

| Variable | Default | Purpose |
|---|---|---|
| `WARP_CLOUD_OLLAMA_BASE_URL` | `""` | Cloud backend URL |
| `WARP_CLOUD_API_KEY` | `""` | Fallback Bearer token |
| `WARP_CLOUD_MODEL_SUFFIX` | `-cloud` | Suffix for cloud routing |
| `WARP_KEYS_FILE_PATH` | `secrets/keys.txt` | API tokens file |
| `WARP_LOCK_FILE_PATH` | `secrets/ollama_keys_lock.txt` | Key lock file (auto-resets every 5h) |
