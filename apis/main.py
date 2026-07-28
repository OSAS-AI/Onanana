import asyncio
import json
import logging
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parents[1]))

from src.onanana.config import settings
from src.onanana.keys_manager import KeysManager
from src.onanana.ollama.openai_compat import (
    iter_ollama_chat_as_openai_sse,
    ollama_chat_to_openai,
    ollama_to_openai_chat_request,
    openai_chat_to_ollama,
    openai_chat_to_ollama_response,
)
from src.onanana.providers.ollama import OllamaProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CLEANUP_INTERVAL = 600  # 10 minutes

km = KeysManager(settings.keys_file_path, cloud_base_url=settings.cloud_ollama_base_url,
                 lock_path=settings.lock_file_path)
km.load_keys()
client = httpx.AsyncClient(timeout=300.0, follow_redirects=True)
provider = OllamaProvider(
    local_base_url=settings.local_ollama_base_url,
    cloud_base_url=settings.cloud_ollama_base_url,
    keys_manager=km,
    client=client,
    cloud_api_key=settings.cloud_api_key,
    lock_path=settings.lock_file_path,
)


async def cleanup_loop():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        removed = km.cleanup_expired_locks()
        if removed:
            logger.info("Auto-cleanup removed %d expired lock(s)", removed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(cleanup_loop())
    yield
    task.cancel()
    await client.aclose()
    await km.close()


app = FastAPI(title="AI Warp Tool", lifespan=lifespan)


@app.exception_handler(RuntimeError)
async def no_key_handler(request: Request, exc: RuntimeError):
    if "No API key available" in str(exc):
        return JSONResponse(status_code=429, content={"error": "No API keys available - all keys locked or missing"})
    return JSONResponse(status_code=500, content={"error": str(exc)})


async def _json_or_empty(resp: httpx.Response) -> Response:
    try:
        await resp.aread()
    except Exception:
        pass
    if not resp.content:
        return Response(status_code=resp.status_code)
    try:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except ValueError:
        return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


async def _cloud_chat_openai(body: dict, *, stream: bool, model: str) -> Response:
    """Cloud chat for OpenAI clients: try /v1 then /api/chat, then retry once more."""
    ollama_body = openai_chat_to_ollama(body)

    for attempt in range(2):
        resp = await provider.proxy_request(
            "v1/chat/completions", body, stream=stream, source="cloud"
        )
        if resp.status_code == 200:
            if stream:
                return StreamingResponse(resp.aiter_bytes(), media_type="text/event-stream")
            return await _json_or_empty(resp)

        if resp.status_code == 403:
            logger.warning("Cloud /v1 403 (attempt %d) — trying /api/chat", attempt + 1)
            try:
                await resp.aread()
            except Exception:
                pass
            resp = await provider.proxy_request(
                "api/chat", ollama_body, stream=stream, source="cloud"
            )
            if resp.status_code == 200:
                if stream:
                    return StreamingResponse(
                        iter_ollama_chat_as_openai_sse(resp, model=ollama_body.get("model") or model),
                        media_type="text/event-stream",
                    )
                await resp.aread()
                return JSONResponse(
                    content=ollama_chat_to_openai(resp.json(), model=ollama_body.get("model") or model),
                    status_code=200,
                )

        # Retry with next key (round-robin advances on each proxy_request).
        if attempt == 0 and resp.status_code == 403:
            logger.warning("Cloud chat still 403 — rotating key and retrying")
            try:
                await resp.aread()
            except Exception:
                pass
            continue
        break

    return await _json_or_empty(resp)


async def _cloud_chat_ollama(body: dict, *, stream: bool) -> Response:
    """Cloud chat for native Ollama clients: try /api/chat then /v1."""
    openai_body = ollama_to_openai_chat_request(body)

    for attempt in range(2):
        resp = await provider.proxy_request("api/chat", body, stream=stream, source="cloud")
        if resp.status_code == 200:
            if stream:
                return StreamingResponse(resp.aiter_bytes(), media_type="application/x-ndjson")
            return await _json_or_empty(resp)

        if resp.status_code == 403:
            logger.warning("Cloud /api/chat 403 (attempt %d) — trying /v1/chat/completions", attempt + 1)
            try:
                await resp.aread()
            except Exception:
                pass
            resp = await provider.proxy_request(
                "v1/chat/completions", openai_body, stream=False, source="cloud"
            )
            # Streaming OpenAI->Ollama conversion is lossy; use one-shot JSON for reliability.
            if stream and resp.status_code == 200:
                await resp.aread()
                ollama_resp = openai_chat_to_ollama_response(resp.json())
                return StreamingResponse(
                    iter([(json.dumps(ollama_resp, ensure_ascii=False) + "\n").encode()]),
                    media_type="application/x-ndjson",
                )
            if resp.status_code == 200:
                await resp.aread()
                return JSONResponse(content=openai_chat_to_ollama_response(resp.json()), status_code=200)

        if attempt == 0 and resp.status_code == 403:
            logger.warning("Cloud chat still 403 — rotating key and retrying")
            try:
                await resp.aread()
            except Exception:
                pass
            continue
        break

    return await _json_or_empty(resp)


@app.get("/api/version")
async def version(source: str = Query("local", pattern="^(local|cloud)$")):
    km.cleanup_expired_locks()
    resp = await provider.proxy_get("api/version", source=source)
    return await _json_or_empty(resp)


@app.get("/api/tags")
async def tags(source: str = Query("local", pattern="^(local|cloud)$")):
    km.cleanup_expired_locks()
    resp = await provider.proxy_get("api/tags", source=source)
    return await _json_or_empty(resp)


@app.get("/api/ps")
async def ps(source: str = Query("local", pattern="^(local|cloud)$")):
    km.cleanup_expired_locks()
    resp = await provider.proxy_get("api/ps", source=source)
    return await _json_or_empty(resp)


@app.head("/api/blobs/{digest}")
async def blob_exists(digest: str, source: str = Query("local", pattern="^(local|cloud)$")):
    km.cleanup_expired_locks()
    resp = await provider.proxy_head(f"api/blobs/{digest}", source=source)
    await resp.aread()
    return Response(status_code=resp.status_code)


@app.post("/api/blobs/{digest}")
async def create_blob(
    digest: str,
    request: Request,
    source: str = Query("local", pattern="^(local|cloud)$"),
):
    km.cleanup_expired_locks()
    content = await request.body()
    resp = await provider.proxy_raw(f"api/blobs/{digest}", content, method="POST", source=source)
    return await _json_or_empty(resp)


@app.post("/v1/{rest:path}")
@app.get("/v1/{rest:path}")
async def openai_proxy(
    request: Request,
    rest: str,
    source: str = Query(None, pattern="^(local|cloud)$"),
):
    """Proxy OpenAI-compatible endpoints with cloud dual-path fallback."""
    km.cleanup_expired_locks()

    try:
        body = await request.json()
    except Exception:
        body = {}

    method = request.method
    model = (body or {}).get("model", "") if isinstance(body, dict) else ""
    use_cloud = source == "cloud" if source else OllamaProvider.is_cloud_model(model)

    if method == "GET":
        if rest == "models" and use_cloud:
            resp = await provider.proxy_get("api/tags", source="cloud")
            await resp.aread()
            if resp.status_code != 200:
                return await _json_or_empty(resp)
            tags_payload = resp.json() if resp.content else {"models": []}
            data = []
            for m in tags_payload.get("models") or []:
                name = m.get("name") or m.get("model") or ""
                if not name:
                    continue
                data.append({
                    "id": name,
                    "object": "model",
                    "created": 0,
                    "owned_by": "ollama",
                })
            return JSONResponse(content={"object": "list", "data": data})
        resp = await provider.proxy_get(f"v1/{rest}", source=source or "local")
        return await _json_or_empty(resp)

    is_stream = bool(body.get("stream", False))

    if rest.rstrip("/") == "chat/completions":
        if use_cloud:
            return await _cloud_chat_openai(body, stream=is_stream, model=model)

        # Local Ollama may lack /v1 — fall back to /api/chat.
        resp = await provider.proxy_request("v1/chat/completions", body, stream=is_stream, source="local")
        if resp.status_code in {404, 405}:
            logger.warning("Local /v1/chat/completions -> %s — falling back to /api/chat", resp.status_code)
            await resp.aread()
            ollama_body = openai_chat_to_ollama(body)
            resp = await provider.proxy_request("api/chat", ollama_body, stream=is_stream, source="local")
            if is_stream:
                return StreamingResponse(
                    iter_ollama_chat_as_openai_sse(resp, model=ollama_body.get("model") or model),
                    media_type="text/event-stream",
                )
            await resp.aread()
            if resp.status_code != 200:
                return await _json_or_empty(resp)
            return JSONResponse(
                content=ollama_chat_to_openai(resp.json(), model=ollama_body.get("model") or model),
                status_code=200,
            )
        if is_stream:
            return StreamingResponse(resp.aiter_bytes(), media_type="text/event-stream")
        return await _json_or_empty(resp)

    resp = await provider.proxy_request(f"v1/{rest}", body, stream=is_stream, source=source)
    if is_stream:
        return StreamingResponse(resp.aiter_bytes(), media_type="text/event-stream")
    return await _json_or_empty(resp)


@app.post("/api/{rest:path}")
@app.get("/api/{rest:path}")
@app.delete("/api/{rest:path}")
async def proxy(
    request: Request,
    rest: str,
    source: str = Query(None, pattern="^(local|cloud)$"),
    prompt: str = Query(None),
    system: str = Query(None),
):
    km.cleanup_expired_locks()

    try:
        body = await request.json()
    except Exception:
        body = {}

    if "messages" in body and "generate" in rest:
        for msg in body["messages"]:
            if msg.get("role") == "system":
                body["system"] = msg["content"]
            elif msg.get("role") == "user":
                body["prompt"] = msg["content"]
        body.pop("messages", None)
        body.pop("message", None)

    method = request.method
    is_stream = body.get("stream", False) if method == "POST" else False
    model = (body or {}).get("model", "") if isinstance(body, dict) else ""
    use_cloud = source == "cloud" if source else OllamaProvider.is_cloud_model(model)

    if method == "GET":
        resp = await provider.proxy_get(f"api/{rest}", source=source or "local")
    elif method == "DELETE":
        resp = await provider.proxy_delete(f"api/{rest}", body, source=source)
    elif method == "POST" and rest.rstrip("/") == "chat" and use_cloud:
        return await _cloud_chat_ollama(body, stream=is_stream)
    else:
        resp = await provider.proxy_request(f"api/{rest}", body, stream=is_stream, source=source)

    if is_stream:
        return StreamingResponse(resp.aiter_bytes(), media_type="application/x-ndjson")
    return await _json_or_empty(resp)


if __name__ == "__main__":
    uvicorn.run("apis.main:app", host=settings.warp_host, port=settings.warp_port)
