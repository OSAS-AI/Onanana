from __future__ import annotations

import json
import time
import uuid
from typing import Any


def openai_chat_to_ollama(body: dict[str, Any]) -> dict[str, Any]:
    """Convert OpenAI /v1/chat/completions body to Ollama /api/chat body."""
    options: dict[str, Any] = {}
    if body.get("temperature") is not None:
        options["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        options["top_p"] = body["top_p"]
    if body.get("max_tokens") is not None:
        options["num_predict"] = body["max_tokens"]
    if body.get("frequency_penalty") is not None:
        options["frequency_penalty"] = body["frequency_penalty"]
    if body.get("presence_penalty") is not None:
        options["presence_penalty"] = body["presence_penalty"]
    if body.get("seed") is not None:
        options["seed"] = body["seed"]
    if body.get("stop") is not None:
        options["stop"] = body["stop"]

    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": body.get("messages") or [],
        "stream": bool(body.get("stream", False)),
    }
    if options:
        out["options"] = options
    if body.get("tools") is not None:
        out["tools"] = body["tools"]
    if body.get("format") is not None:
        out["format"] = body["format"]
    elif isinstance(body.get("response_format"), dict):
        fmt = body["response_format"]
        if fmt.get("type") == "json_object":
            out["format"] = "json"
    return out


def ollama_chat_to_openai(resp: dict[str, Any], *, model: str | None = None) -> dict[str, Any]:
    """Convert a non-streaming Ollama /api/chat response to OpenAI chat.completion."""
    message = resp.get("message") or {"role": "assistant", "content": ""}
    prompt_tokens = int(resp.get("prompt_eval_count") or 0)
    completion_tokens = int(resp.get("eval_count") or 0)
    finish = "stop"
    if resp.get("done_reason") == "length":
        finish = "length"
    elif message.get("tool_calls"):
        finish = "tool_calls"

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or resp.get("model") or "",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": message.get("content") or "",
                    **({"tool_calls": message["tool_calls"]} if message.get("tool_calls") else {}),
                },
                "finish_reason": finish,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def ollama_chat_chunk_to_openai_sse(chunk: dict[str, Any], *, model: str, chunk_id: str) -> bytes:
    """Convert one Ollama NDJSON chat chunk to an OpenAI SSE data line."""
    message = chunk.get("message") or {}
    content = message.get("content") or ""
    done = bool(chunk.get("done"))
    delta: dict[str, Any] = {}
    finish_reason = None
    if not done:
        if content:
            delta = {"content": content}
        if message.get("tool_calls"):
            delta["tool_calls"] = message["tool_calls"]
        if message.get("role") and not content and not message.get("tool_calls"):
            delta = {"role": message["role"]}
    else:
        finish_reason = "stop"
        if chunk.get("done_reason") == "length":
            finish_reason = "length"
        if content:
            delta = {"content": content}

    payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


async def iter_ollama_chat_as_openai_sse(resp, *, model: str):
    """Yield OpenAI SSE bytes from a streaming Ollama /api/chat response."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    async for line in resp.aiter_lines():
        line = (line or "").strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        yield ollama_chat_chunk_to_openai_sse(data, model=model, chunk_id=chunk_id)
        if data.get("done"):
            break
    yield b"data: [DONE]\n\n"
