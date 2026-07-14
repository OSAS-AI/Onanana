# Usage

## Prerequisites

- **Local** — [Ollama](https://ollama.com) must be installed and running on the target host (default `http://localhost:11434`). Start it with `ollama serve`.
- **Cloud** — one or more API keys saved in `secrets/keys.txt` (one per line). See [`secrets/keys.txt.example`](../secrets/keys.txt.example) for the format. Comments and blank lines are ignored.

## Setup

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install runtime deps
pip install -r requirements\requirements-base.txt

# Or include dev/test deps
pip install -r requirements\requirements-dev.txt
```

## Configuration

Settings are loaded from `secrets/.env` and environment variables (env vars take precedence).

### Cloud endpoint

Set in `secrets/.env`:

```ini
WARP_CLOUD_OLLAMA_BASE_URL=https://your-cloud-api.example.com
WARP_CLOUD_API_KEY=sk-your-fallback-key
```

Or as environment variables:

```powershell
$env:WARP_CLOUD_OLLAMA_BASE_URL="https://your-cloud-api.example.com"
$env:WARP_CLOUD_API_KEY="sk-your-fallback-key"
```

### API keys

Place Bearer tokens in `secrets/keys.txt`, one per line:

```
sk-abc123...
sk-def456...
sk-ghi789...
```

Tokens are used in round-robin order with automatic health checking. Tokens that get a `429` (rate limited) or time out 3 consecutive times are auto-locked into `secrets/ollama_keys_lock.txt` so they won't be reused.

Locked keys are automatically unlocked in **3 ways**:

1. **Background cleanup** — a background task runs every **10 minutes** and removes expired entries from the lock file.
2. **On each request** — every endpoint handler checks the lock file before processing, so expired keys become available immediately.
3. **Lock file expiry** — each locked entry has a 5-hour timestamp. Entries older than **5 hours** are automatically purged when the lock file is read.

When all keys are locked, the proxy returns `429` instead of `500`.

If `keys.txt` is empty or missing, the fallback `WARP_CLOUD_API_KEY` env var is used.

### Cloud model suffix

Any model name ending in `-cloud` routes to the cloud backend (suffix stripped before forwarding). This is hardcoded in `src/onanana/providers/ollama.py`.

### Local Ollama

Make sure Ollama is running locally on port 11434:

```powershell
ollama serve
```

## Running

```powershell
python -m uvicorn apis.main:app --host 0.0.0.0 --port 11435
```

Or with reload during development:

```powershell
python -m uvicorn apis.main:app --reload --host 0.0.0.0 --port 11435
```

## Checking it works

```powershell
# Check local (no local Ollama? will get 502 — that's expected)
python -c "import requests; r = requests.get('http://localhost:11435/api/version', params={'source': 'local'}); print(r.status_code, r.text[:100])"

# Check cloud
python -c "import requests; r = requests.get('http://localhost:11435/api/version', params={'source': 'cloud'}); print(r.status_code, r.text[:100])"

# List models (local)
python -c "import requests; r = requests.get('http://localhost:11435/api/tags', params={'source': 'local'}); print(r.status_code, [m['name'] for m in r.json().get('models', [])])"

# List models (cloud)
python -c "import requests; r = requests.get('http://localhost:11435/api/tags', params={'source': 'cloud'}); print(r.status_code, [m['name'] for m in r.json().get('models', [])])"
```

## Using the package directly

The `src/onanana/` package can be used in your own scripts without starting the proxy server.

### KeysManager

```python
from src.onanana.keys_manager import KeysManager

km = KeysManager("secrets/keys.txt", cloud_base_url="https://your-cloud-api.example.com")
km.load_keys()
key = await km.get_next_healthy_key()  # returns a token or None
await km.close()
```

### OllamaProvider

```python
import httpx
from src.onanana.keys_manager import KeysManager
from src.onanana.providers.ollama import OllamaProvider

km = KeysManager("secrets/keys.txt", cloud_base_url="https://your-cloud-api.example.com")
km.load_keys()

async with httpx.AsyncClient(timeout=300.0) as client:
    provider = OllamaProvider(
        local_base_url="http://localhost:11434",
        cloud_base_url="https://your-cloud-api.example.com",
        keys_manager=km,
        client=client,
    )
    resp = await provider.proxy_get("api/tags", source="local")
    print(resp.json())
```

### OllamaRequestBuilder

```python
import httpx
from src.onanana.ollama.request import OllamaRequestBuilder

client = httpx.AsyncClient()
builder = OllamaRequestBuilder(client)
req = builder.build_request("api/chat", "http://localhost:11434", {"model": "gemma4:26b", "messages": []})

async with client:
    resp = await builder.send_request("api/chat", "http://localhost:11434", {"model": "gemma4:26b", "messages": []})
    print(resp.json())
```

### Models

```python
from src.onanana.ollama.models import ChatRequest, GenerateRequest

req = ChatRequest(model="gemma4:26b", messages=[{"role": "user", "content": "hi"}])
print(req.model_dump_json(indent=2))
```

## Examples

```powershell
python examples/chat_stream.py
python examples/chat_ollama_api_key.py
```

Or call the proxy directly:

```python
import requests

# Chat — local model
r = requests.post("http://localhost:11435/api/chat", json={
    "model": "gemma4:26b",
    "messages": [{"role": "user", "content": "hello"}],
    "stream": False,
})

# Chat — cloud model (via -cloud suffix)
r = requests.post("http://localhost:11435/api/chat", json={
    "model": "gemma4:31b-cloud",
    "messages": [{"role": "user", "content": "hello"}],
    "stream": False,
})
```

See [`examples/ai_warp_tool_api.ipynb`](../examples/ai_warp_tool_api.ipynb) for a full interactive walkthrough.

## Expected status codes

| Scenario | Status |
|---|---|
| Local endpoint, Ollama running | `200` |
| Local endpoint, no Ollama | `502` |
| Cloud endpoint, configured | `200` |
| Cloud endpoint, URL missing | `503` — "Cloud base URL not configured" |
| Cloud endpoint, key missing | `503` — "No API key available" |
| All cloud keys locked | `429` — "No API keys available - all keys locked or missing" |
| Invalid `?source=` value | `422` |

## Shutdown

```powershell
# Stop the uvicorn process (Ctrl+C in the terminal)
# Or kill the process on port 11435
Stop-Process -Id (Get-NetTCPConnection -LocalPort 11435).OwningProcess -Force
```
