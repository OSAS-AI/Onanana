# Package

```
src/onanana/
├── __init__.py
├── config.py              Pydantic settings from WARP_ env vars (load_dotenv secrets/.env)
├── keys_manager.py        Loads & health-checks Bearer tokens from keys.txt, key locking
├── ollama/
│   ├── models.py          Pydantic schemas for all Ollama request/response types
│   └── request.py         OllamaRequestBuilder — constructs & sends httpx requests
└── providers/
    └── ollama.py          OllamaProvider — core proxy logic, routing, auth, retry, key bans
```

The `src/onanana/` package was extracted from the FastAPI app so its logic can be unit-tested without an HTTP server. The FastAPI app in `apis/main.py` uses the same package directly.

## Modules

### `config.py`

```python
from src.onanana.config import settings

settings.cloud_ollama_base_url
settings.cloud_api_key
settings.cloud_model_suffix    # "-cloud" (defined but not wired to provider yet)
settings.keys_file_path
settings.local_ollama_base_url
settings.short_lock_file_path  # secrets/ollama_shorttime_keys_lock.txt
settings.long_lock_file_path   # secrets/ollama_longtime_keys_lock.txt
```

Reads from `WARP_*` env vars. Call `load_dotenv("secrets/.env")` at import to load from file.

### `keys_manager.py`

Loads Bearer tokens from `secrets/keys.txt` and provides round-robin selection with optional health-checking. Filters out locked keys (from lock files).

```python
km = KeysManager("secrets/keys.txt", cloud_base_url="https://...")
km.load_keys()
key = await km.get_next_healthy_key()  # or None
```

### `providers/ollama.py`

Core proxy logic. Resolves routing, injects auth headers, forwards requests. Features:
- Retry (3 attempts) on timeout with auto-lock of failing keys
- Cloud suffix stripping (`-cloud`) and detection

```python
provider = OllamaProvider(
    local_base_url="http://localhost:11434",
    cloud_base_url="https://...",
    keys_manager=km,
    cloud_api_key="...",
)

await provider.proxy_get("api/tags", source="local")
await provider.proxy_get("api/tags", source="cloud")
await provider.proxy_request("/api/chat", body, stream=False, source=None)
await provider.proxy_delete("/api/delete", body, source=None)
```

### `ollama/models.py`

Pydantic models: `GenerateRequest`, `ChatRequest`, `EmbedRequest`, `PullRequest`, `PushRequest`, `CreateRequest`, `ShowRequest`, `CopyRequest`, `DeleteRequest`, `GenerateResponse`, `ChatResponse`, `EmbedResponse`, `TagsResponse`, `VersionResponse`, `OllamaError`, `ModelInfo`, `Message`.

### `ollama/request.py`

Builds and sends `httpx.Request` objects. Determines HTTP method per endpoint, extracts `model` and `stream` fields.

## Tests

```bash
python -m pytest tests/check_ai_warp_tool_api.py -v
```

23 tests covering:
- All API endpoints (version, tags, chat, generate, streaming, delete)
- Routing via model suffix and `?source=` param
- Error handling (invalid source, missing cloud auth)
- Provider methods directly (suffix stripping, proxy calls, auth resolution)
