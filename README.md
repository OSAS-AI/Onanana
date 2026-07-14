# AI Warp Tool

Ollama-compatible proxy on `:11435` that routes requests to local Ollama or a cloud API.

```
Client -> :11435 -> OllamaProvider -> localhost:11434 (no auth)
                                   -> cloud URL (Bearer token)
```

Routing is determined by **model name suffix** (default `-cloud`) or **`?source=` query param**.

## Quick start

```bash
pip install -r requirements/requirements-base.txt
python -m uvicorn apis.main:app --host 0.0.0.0 --port 11435
```

## How routing works

| Model name | Default route | model sent to backend |
|---|---|---|
| `gemma4:26b` | local (`:11434`) | `gemma4:26b` |
| `gemma4:31b-cloud` | cloud | `gemma4:31b` (suffix stripped) |
| any + `?source=local` | local | original name kept, even with `-cloud` suffix |
| any + `?source=cloud` | cloud | suffix stripped if present |

The cloud suffix is `-cloud` (hardcoded in `src/onanana/providers/ollama.py`).

Cloud auth: token from `secrets/keys.txt` (round-robin with health checks) → `WARP_CLOUD_API_KEY` env var → `503`.

## Configuration

`WARP_` env vars or `secrets/.env` file (see `src/onanana/config.py`):

| Variable | Default | Description |
|---|---|---|
| `WARP_HOST` | `0.0.0.0` | Bind address |
| `WARP_PORT` | `11435` | Listen port |
| `WARP_LOCAL_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama |
| `WARP_CLOUD_OLLAMA_BASE_URL` | `""` | Cloud API endpoint |
| `WARP_CLOUD_API_KEY` | `""` | Fallback Bearer token |
| `WARP_KEYS_FILE_PATH` | `secrets/keys.txt` | API tokens file |
| `WARP_CLOUD_MODEL_SUFFIX` | `-cloud` | Suffix for cloud model routing (defined in config, wired in source) |

## Architecture

```
apis/main.py                  FastAPI app, imports src/ package
src/onanana/
  config.py                   Pydantic settings (load_dotenv secrets/.env)
  keys_manager.py             Loads tokens, round-robin, health checks, key locking
  providers/ollama.py         OllamaProvider — proxy methods with retry & timeout key bans
  ollama/
    models.py                 Pydantic schemas (request/response)
    request.py                Request builder
examples/
  use_pakage.ipynb            Interactive package usage examples
  ai_warp_tool_api.ipynb      Interactive API endpoint examples
  chat_stream.py              Chat via the proxy
  chat_ollama_api_key.py      Direct cloud API call with key
tests/
  check_ai_warp_tool_api.py  23 tests for API endpoints & provider
```

## Examples

```bash
# Chat (streaming) via the proxy
python examples/chat_stream.py

# Direct cloud API call with key
python examples/chat_ollama_api_key.py
```

See [`examples/use_pakage.ipynb`](examples/use_pakage.ipynb) and [`examples/ai_warp_tool_api.ipynb`](examples/ai_warp_tool_api.ipynb) for interactive examples.
