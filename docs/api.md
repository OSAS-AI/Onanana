# API Reference

Base: `http://localhost:11435`

All endpoints match the [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md).

## Routing

| Backend | Base URL | Auth |
|---|---|---|
| Local | `http://localhost:11434` | None |
| Cloud | `WARP_CLOUD_OLLAMA_BASE_URL` | `Authorization: Bearer <token>` |

### Rules

1. **Model suffix** — model ending in the configured suffix (default `-cloud`) routes to cloud; suffix is stripped before forwarding
2. **`?source=` param** — overrides model-based routing. `?source=local` forces local (model name kept as-is). `?source=cloud` forces cloud (suffix stripped). Invalid values → `422`

Cloud requires URL + token. Missing either → `503`.

## Model name behavior

| Request | Route | model forwarded |
|---|---|---|
| `model: "gemma4:26b"` | local | `gemma4:26b` |
| `model: "gemma4:31b-cloud"` | cloud | `gemma4:31b` |
| `model: "gemma4:31b-cloud", ?source=local` | local | `gemma4:31b-cloud` (kept) |
| `model: "gemma4:26b", ?source=cloud` | cloud | `gemma4:26b` |

The suffix is configurable via `WARP_CLOUD_MODEL_SUFFIX` (default `-cloud`).

## Endpoints

### `GET /api/version`

```python
r = requests.get("http://localhost:11435/api/version")
r = requests.get("http://localhost:11435/api/version?source=cloud")
```

### `GET /api/tags`

```python
r = requests.get("http://localhost:11435/api/tags")
r = requests.get("http://localhost:11435/api/tags?source=cloud")
```

### `GET /api/ps`

List models currently loaded into memory.

```python
r = requests.get("http://localhost:11435/api/ps")
r = requests.get("http://localhost:11435/api/ps?source=cloud")
```

### `POST /api/{chat,generate,embed,embeddings,create,pull,push,show,copy}`

```python
import requests

# Local model
r = requests.post("http://localhost:11435/api/chat", json={
    "model": "gemma4:26b",
    "messages": [{"role": "user", "content": "hi"}],
})

# Cloud via -cloud suffix
r = requests.post("http://localhost:11435/api/chat", json={
    "model": "gemma4:31b-cloud",
    "messages": [{"role": "user", "content": "hi"}],
})

# Cloud via ?source=
r = requests.post("http://localhost:11435/api/generate?source=cloud", json={
    "model": "gemma4:26b",
    "prompt": "hello",
})
```

**Note:** The `/api/generate` endpoint accepts `messages` in the same format as `/api/chat`. The proxy converts `messages` → `prompt`/`system` before forwarding.

```python
r = requests.post("http://localhost:11435/api/generate", json={
    "model": "gemma4:31b-cloud",
    "messages": [
        {"role": "system", "content": "You are a pirate."},
        {"role": "user", "content": "What is the capital of France?"},
    ],
    "stream": False,
})
```

#### Embeddings

Prefer `/api/embed` (`input`). Legacy `/api/embeddings` (`prompt`) is still forwarded.

```python
r = requests.post("http://localhost:11435/api/embed", json={
    "model": "embeddinggemma",
    "input": "hello world",
})

r = requests.post("http://localhost:11435/api/embeddings", json={
    "model": "all-minilm",
    "prompt": "hello world",
})
```

Streaming responses pass through transparently (`GET` endpoints do not support streaming).

### `HEAD /api/blobs/{digest}` / `POST /api/blobs/{digest}`

Check whether a blob exists, or upload a raw blob body (used when creating models).

```python
digest = "sha256:29fdb92e57cf0827ded04ae6461b5931d01fa595843f55d36f5b275a52087dd2"

r = requests.head(f"http://localhost:11435/api/blobs/{digest}")
# 200 if present, 404 if missing

with open("model.bin", "rb") as f:
    r = requests.post(f"http://localhost:11435/api/blobs/{digest}", data=f)
# 201 Created on success
```

### `DELETE /api/delete`

```python
r = requests.delete("http://localhost:11435/api/delete", json={"model": "gemma4:26b"})
```

## OpenAI compatibility (`/v1`)

Proxied to the backend Ollama OpenAI-compatible API. Same local/cloud routing rules apply (`-cloud` suffix or `?source=`).

Base for OpenAI SDKs: `http://localhost:11435/v1`

| Endpoint | Method |
|---|---|
| `/v1/chat/completions` | POST |
| `/v1/completions` | POST |
| `/v1/embeddings` | POST |
| `/v1/models` | GET |
| `/v1/models/{model}` | GET |

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11435/v1",
    api_key="ollama",  # required by SDK, ignored locally
)

# Chat
r = client.chat.completions.create(
    model="gemma4:26b",
    messages=[{"role": "user", "content": "hi"}],
)

# Cloud via -cloud suffix
r = client.chat.completions.create(
    model="gemma4:31b-cloud",
    messages=[{"role": "user", "content": "hi"}],
)

# Completions
r = client.completions.create(model="gemma4:26b", prompt="Once upon a time")

# Embeddings
r = client.embeddings.create(model="embeddinggemma", input="hello world")

# List models
r = client.models.list()
```

Or with `requests`:

```python
r = requests.post("http://localhost:11435/v1/chat/completions", json={
    "model": "gemma4:26b",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": False,
})

# Streaming uses SSE (text/event-stream)
r = requests.post("http://localhost:11435/v1/chat/completions", json={
    "model": "gemma4:26b",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": True,
}, stream=True)

r = requests.get("http://localhost:11435/v1/models")
r = requests.get("http://localhost:11435/v1/models?source=cloud")
```

## Errors

| Status | Meaning |
|---|---|
| `429` | All cloud keys locked or none available |
| `502` | Backend unreachable |
| `503` | Cloud URL or key missing |
| `504` | Backend timed out |
| `422` | Invalid `source` value |

## Auth

1. `secrets/keys.txt` (round-robin with health checks)
2. `WARP_CLOUD_API_KEY` env var
3. `503` if neither

### Key locking

Keys are auto-locked on `429` responses or 3 consecutive timeouts. Locked keys are stored in
`secrets/ollama_keys_lock.txt` with a timestamp. Unlocking happens automatically via:
- Background cleanup every **10 minutes**
- Lock file check on **every endpoint call**
- **5-hour expiry** of lock entries
