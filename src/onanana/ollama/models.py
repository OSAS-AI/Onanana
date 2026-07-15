from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    model: str
    prompt: str = ""
    system: str | None = None
    template: str | None = None
    context: list[int] | None = None
    stream: bool = True
    raw: bool | None = None
    format: str | None = None
    images: list[str] | None = None
    options: dict[str, Any] | None = None


class GenerateResponse(BaseModel):
    model: str
    created_at: str = ""
    response: str = ""
    done: bool = False
    context: list[int] | None = None
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None


class Message(BaseModel):
    role: str
    content: str
    images: list[str] | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    model: str
    messages: list[Message] = Field(default_factory=list)
    stream: bool = True
    format: str | None = None
    options: dict[str, Any] | None = None
    template: str | None = None


class ChatResponse(BaseModel):
    model: str
    created_at: str = ""
    message: Message | None = None
    done: bool = False
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None


class EmbedRequest(BaseModel):
    model: str
    input: str | list[str]
    truncate: bool | None = None
    options: dict[str, Any] | None = None
    keep_alive: str | float | None = None
    dimensions: int | None = None


class EmbedResponse(BaseModel):
    model: str
    embeddings: list[list[float]] = Field(default_factory=list)
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None


class EmbeddingsRequest(BaseModel):
    """Legacy `/api/embeddings` request (superseded by `/api/embed`)."""

    model: str
    prompt: str = ""
    options: dict[str, Any] | None = None
    keep_alive: str | float | None = None


class EmbeddingsResponse(BaseModel):
    embedding: list[float] = Field(default_factory=list)


class PullRequest(BaseModel):
    model: str
    insecure: bool = False
    stream: bool = True


class PushRequest(BaseModel):
    model: str
    insecure: bool = False
    stream: bool = True


class CreateRequest(BaseModel):
    model: str
    from_: str | None = Field(None, alias="from")
    modelfile: str | None = None
    stream: bool = True

    model_config = {"populate_by_name": True}


class ShowRequest(BaseModel):
    model: str
    verbose: bool | None = None


class CopyRequest(BaseModel):
    source: str
    destination: str


class DeleteRequest(BaseModel):
    model: str


class ModelInfo(BaseModel):
    name: str
    modified_at: str = ""
    size: int = 0
    digest: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class RunningModel(BaseModel):
    name: str = ""
    model: str = ""
    size: int = 0
    digest: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    expires_at: str = ""
    size_vram: int = 0
    context_length: int | None = None


class TagsResponse(BaseModel):
    models: list[ModelInfo] = Field(default_factory=list)


class PsResponse(BaseModel):
    models: list[RunningModel] = Field(default_factory=list)


class VersionResponse(BaseModel):
    version: str = ""


class OllamaError(BaseModel):
    error: str
