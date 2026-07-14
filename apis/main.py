import logging
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.onanana.config import settings
from src.onanana.keys_manager import KeysManager
from src.onanana.providers.ollama import OllamaProvider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

km = KeysManager(settings.keys_file_path, cloud_base_url=settings.cloud_ollama_base_url,
                 short_lock_path=settings.short_lock_file_path,
                 long_lock_path=settings.long_lock_file_path)
km.load_keys()
client = httpx.AsyncClient(timeout=300.0)
provider = OllamaProvider(
    local_base_url=settings.local_ollama_base_url,
    cloud_base_url=settings.cloud_ollama_base_url,
    keys_manager=km,
    client=client,
    cloud_api_key=settings.cloud_api_key,
    short_lock_path=settings.short_lock_file_path,
    long_lock_path=settings.long_lock_file_path,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client.aclose()
    await km.close()


app = FastAPI(title="AI Warp Tool", lifespan=lifespan)


@app.get("/api/version")
async def version(source: str = Query("local", pattern="^(local|cloud)$")):
    resp = await provider.proxy_get("api/version", source=source)
    await resp.aread()
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


@app.get("/api/tags")
async def tags(source: str = Query("local", pattern="^(local|cloud)$")):
    resp = await provider.proxy_get("api/tags", source=source)
    await resp.aread()
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


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
    await resp.aread()
    return JSONResponse(content=resp.json(), status_code=resp.status_code)


if __name__ == "__main__":
    uvicorn.run("apis.main:app", host=settings.warp_host, port=settings.warp_port)
