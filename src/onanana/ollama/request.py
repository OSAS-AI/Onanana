from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from src.onanana.ollama.models import (
    ChatRequest,
    CopyRequest,
    CreateRequest,
    DeleteRequest,
    EmbeddingsRequest,
    EmbedRequest,
    GenerateRequest,
    PullRequest,
    PushRequest,
    ShowRequest,
)

logger = logging.getLogger(__name__)

ENDPOINTS = {
    "generate": {"method": "POST", "model": GenerateRequest},
    "chat": {"method": "POST", "model": ChatRequest},
    "embed": {"method": "POST", "model": EmbedRequest},
    "embeddings": {"method": "POST", "model": EmbeddingsRequest},
    "create": {"method": "POST", "model": CreateRequest},
    "pull": {"method": "POST", "model": PullRequest},
    "push": {"method": "POST", "model": PushRequest},
    "show": {"method": "POST", "model": ShowRequest},
    "copy": {"method": "POST", "model": CopyRequest},
    "delete": {"method": "DELETE", "model": DeleteRequest},
    "tags": {"method": "GET", "model": None},
    "version": {"method": "GET", "model": None},
    "ps": {"method": "GET", "model": None},
}


class OllamaRequestBuilder:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    def build_request(
        self,
        path: str,
        base_url: str,
        body: dict[str, Any] | None,
        *,
        method: str | None = None,
        model_override: str | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Request:
        api_path = path.lstrip("/")
        url = f"{base_url.rstrip('/')}/{api_path}"
        resolved_method = (method or self._method_for_path(api_path)).upper()

        req_headers = dict(headers) if headers else None
        kwargs: dict[str, Any] = {"headers": req_headers}

        if content is not None:
            kwargs["content"] = content
        elif resolved_method in {"POST", "PUT", "PATCH", "DELETE"}:
            payload = dict(body) if body else {}
            if model_override is not None:
                payload["model"] = model_override
            kwargs["json"] = payload
        elif body and model_override is not None:
            payload = dict(body)
            payload["model"] = model_override
            kwargs["json"] = payload

        logger.debug("Building %s %s", resolved_method, url)
        return self._client.build_request(resolved_method, url, **kwargs)

    async def send_request(
        self,
        path: str,
        base_url: str,
        body: dict[str, Any] | None,
        *,
        method: str | None = None,
        model_override: str | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        stream: bool = True,
    ) -> httpx.Response:
        req = self.build_request(
            path,
            base_url,
            body,
            method=method,
            model_override=model_override,
            headers=headers,
            content=content,
        )
        return await self._client.send(req, stream=stream)

    @staticmethod
    def _method_for_path(api_path: str) -> str:
        # Prefer exact endpoint name matches over blob path prefixes.
        for name, info in ENDPOINTS.items():
            if api_path.endswith(f"/api/{name}") or api_path == f"api/{name}":
                return info["method"]
        if "/api/blobs/" in f"/{api_path}" or api_path.startswith("api/blobs/"):
            return "POST"
        return "POST"

    @staticmethod
    def parse_model_field(body: dict[str, Any] | None) -> str:
        return (body or {}).get("model", "")

    @staticmethod
    def is_streaming(body: dict[str, Any] | None) -> bool:
        return bool((body or {}).get("stream", False))

    @staticmethod
    def serialize_stream_chunk(data: dict[str, Any]) -> bytes:
        return (json.dumps(data, ensure_ascii=False) + "\n").encode()
