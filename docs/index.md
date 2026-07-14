# AI Warp Tool

Ollama-compatible proxy on `:11435` for local + cloud model routing.

```
Client -> :11435 -> OllamaProvider -> localhost:11434 (no auth)
                                   -> cloud URL (Bearer token)
```

- [API Reference](api.md) — endpoints, routing rules, error codes
- [Package](package.md) — `src/onanana/` modules
- [Usage](usage.md) — setup, config, examples

## Quick start

```bash
pip install -r requirements/requirements-base.txt
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
| `WARP_SHORT_LOCK_FILE_PATH` | `secrets/ollama_shorttime_keys_lock.txt` | Short-term key ban file |
| `WARP_LONG_LOCK_FILE_PATH` | `secrets/ollama_longtime_keys_lock.txt` | Long-term key ban file |
