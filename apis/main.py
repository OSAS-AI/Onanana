import asyncio
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
    openai_chat_to_ollama,
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
    await resp.aread()
    if not resp.content:
        return Response(status_code=resp.status_code)
    try:
        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except ValueError:
        return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))


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
    """Proxy OpenAI-compatible endpoints.

    For cloud chat/completions: try /v1 first, fall back to native /api/chat
    because ollama.com intermittently returns 403 on one path or the other.
    """
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
            tags = resp.json() if resp.content else {"models": []}
            data = []
            for m in tags.get("models") or []:
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

    if use_cloud and rest.rstrip("/") == "chat/completions":
        # Prefer native OpenAI path; fall back to /api/chat on 403.
        resp = await provider.proxy_request(
            "v1/chat/completions", body, stream=is_stream, source="cloud"
        )
        if resp.status_code == 403:
            logger.warning("Cloud /v1/chat/completions returned 403 — falling back to /api/chat")
            await resp.aread()
            ollama_body = openai_chat_to_ollama(body)
            resp = await provider.proxy_request(
                "api/chat", ollama_body, stream=is_stream, source="cloud"
            )
            if is_stream:
                return StreamingResponse(
                    iter_ollama_chat_as_openai_sse(resp, model=ollama_body.get("model") or model),
                    media_type="text/event-stream",
                )
            await resp.aread()
            if resp.status_code != 200:
                return await _json_or_empty(resp)
            try:
                raw = resp.json()
            except ValueError:
                return Response(content=resp.content, status_code=resp.status_code)
            return JSONResponse(
                content=ollama_chat_to_openai(raw, model=ollama_body.get("model") or model),
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

    if method == "GET":
        resp = await provider.proxy_get(f"api/{rest}", source=source or "local")
    elif method == "DELETE":
        resp = await provider.proxy_delete(f"api/{rest}", body, source=source)
    else:
        resp = await provider.proxy_request(f"api/{rest}", body, stream=is_stream, source=source)

    if is_stream:
        return StreamingResponse(resp.aiter_bytes(), media_type="application/x-ndjson")
    return await _json_or_empty(resp)


if __name__ == "__main__":
    uvicorn.run("apis.main:app", host=settings.warp_host, port=settings.warp_port)
