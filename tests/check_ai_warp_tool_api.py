import json
import pytest
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from src.onanana.keys_manager import KeysManager
from src.onanana.providers.ollama import OllamaProvider


def _mock_transport(**kwargs):
    return httpx.MockTransport(lambda r: httpx.Response(200, json=kwargs or {"version": "0.0.0"}))


@pytest.fixture
def mock_client():
    return httpx.AsyncClient(transport=_mock_transport())


@pytest.fixture
def test_app(mock_client, monkeypatch):
    mock_km = KeysManager("secrets/keys.txt", cloud_base_url="")
    mock_km._keys = ["sk-test-key"]
    mock_km._healthy_keys = ["sk-test-key"]

    mock_prov = OllamaProvider(
        local_base_url="http://localhost:11434",
        cloud_base_url="https://api.ollama.com",
        keys_manager=mock_km,
        client=mock_client,
        cloud_api_key="sk-fallback",
    )

    monkeypatch.setattr("apis.main.km", mock_km)
    monkeypatch.setattr("apis.main.provider", mock_prov)

    from apis.main import app
    with TestClient(app) as client:
        yield client


class TestVersionEndpoint:
    def test_get_version_local(self, test_app):
        resp = test_app.get("/api/version?source=local")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.0.0"

    def test_get_version_cloud(self, test_app):
        resp = test_app.get("/api/version?source=cloud")
        assert resp.status_code == 200

    def test_get_version_default_local(self, test_app):
        resp = test_app.get("/api/version")
        assert resp.status_code == 200


class TestTagsEndpoint:
    def test_list_tags_local(self, test_app):
        resp = test_app.get("/api/tags?source=local")
        assert resp.status_code == 200

    def test_list_tags_cloud(self, test_app):
        resp = test_app.get("/api/tags?source=cloud")
        assert resp.status_code == 200


class TestPsEndpoint:
    def test_list_ps_local(self, test_app):
        resp = test_app.get("/api/ps?source=local")
        assert resp.status_code == 200

    def test_list_ps_cloud(self, test_app):
        resp = test_app.get("/api/ps?source=cloud")
        assert resp.status_code == 200

    def test_list_ps_default_local(self, test_app):
        resp = test_app.get("/api/ps")
        assert resp.status_code == 200


class TestEmbedEndpoint:
    def test_embed_local(self, test_app):
        resp = test_app.post("/api/embed", json={
            "model": "embeddinggemma",
            "input": "hello",
        })
        assert resp.status_code == 200

    def test_embeddings_legacy_local(self, test_app):
        resp = test_app.post("/api/embeddings", json={
            "model": "all-minilm",
            "prompt": "hello",
        })
        assert resp.status_code == 200

    def test_embed_cloud_via_source(self, test_app):
        resp = test_app.post("/api/embed?source=cloud", json={
            "model": "embeddinggemma",
            "input": ["hello", "world"],
        })
        assert resp.status_code == 200


class TestBlobsEndpoint:
    def test_blob_head_local(self, test_app):
        digest = "sha256:29fdb92e57cf0827ded04ae6461b5931d01fa595843f55d36f5b275a52087dd2"
        resp = test_app.head(f"/api/blobs/{digest}?source=local")
        assert resp.status_code == 200

    def test_blob_create_local(self, test_app):
        digest = "sha256:29fdb92e57cf0827ded04ae6461b5931d01fa595843f55d36f5b275a52087dd2"
        resp = test_app.post(f"/api/blobs/{digest}?source=local", content=b"blob-bytes")
        assert resp.status_code == 200


class TestChatEndpoint:
    def test_chat_local_model(self, test_app):
        resp = test_app.post("/api/chat", json={
            "model": "gemma4:26b",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        assert resp.status_code == 200

    def test_chat_cloud_model_suffix(self, test_app):
        resp = test_app.post("/api/chat", json={
            "model": "gemma4:31b-cloud",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        assert resp.status_code == 200

    def test_chat_cloud_via_source_param(self, test_app):
        resp = test_app.post("/api/chat?source=cloud", json={
            "model": "gemma4:26b",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        assert resp.status_code == 200

    def test_chat_source_local_overrides_suffix(self, test_app):
        resp = test_app.post("/api/chat?source=local", json={
            "model": "gemma4:31b-cloud",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        assert resp.status_code == 200


class TestGenerateEndpoint:
    def test_generate_local(self, test_app):
        resp = test_app.post("/api/generate", json={
            "model": "gemma4:26b",
            "prompt": "hello",
            "stream": False,
        })
        assert resp.status_code == 200

    def test_generate_cloud(self, test_app):
        resp = test_app.post("/api/generate?source=cloud", json={
            "model": "gemma4:26b",
            "prompt": "hello",
            "stream": False,
        })
        assert resp.status_code == 200


class TestStreamingEndpoint:
    def test_chat_streaming(self, test_app):
        resp = test_app.post("/api/chat", json={
            "model": "gemma4:26b",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-ndjson"


class TestDeleteEndpoint:
    def test_delete_local(self, test_app):
        body = json.dumps({"model": "gemma4:26b"})
        resp = test_app.request("DELETE", "/api/delete", content=body)
        assert resp.status_code == 200

    def test_delete_cloud(self, test_app):
        body = json.dumps({"model": "gemma4:26b"})
        resp = test_app.request("DELETE", "/api/delete?source=cloud", content=body)
        assert resp.status_code == 200


class TestInvalidInputs:
    def test_invalid_source_value(self, test_app):
        resp = test_app.get("/api/version?source=invalid")
        assert resp.status_code == 422

    def test_empty_body(self, test_app):
        resp = test_app.post("/api/chat")
        assert resp.status_code == 200


class TestSuffixConfig:
    def test_default_suffix_is_cloud(self):
        assert OllamaProvider.is_cloud_model("gemma4:31b-cloud") is True
        assert OllamaProvider.is_cloud_model("gemma4:26b") is False
        assert OllamaProvider.is_cloud_model("") is False

    def test_strip_suffix(self):
        assert OllamaProvider.strip_cloud_suffix("gemma4:31b-cloud") == "gemma4:31b"
        assert OllamaProvider.strip_cloud_suffix("gemma4:26b") == "gemma4:26b"


@pytest.mark.asyncio
async def test_proxy_get_local():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"models": []}))
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt")
        km._keys = []
        km._healthy_keys = []
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="",
            keys_manager=km,
            client=client,
        )
        resp = await prov.proxy_get("api/tags", source="local")
        assert resp.status_code == 200
        assert resp.json() == {"models": []}


@pytest.mark.asyncio
async def test_proxy_get_cloud_no_key_raises():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt", cloud_base_url="")
        km._keys = []
        km._healthy_keys = []
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="https://cloud.example.com",
            keys_manager=km,
            client=client,
            cloud_api_key="",
        )
        with pytest.raises(RuntimeError, match="No API key available"):
            await prov.proxy_get("api/tags", source="cloud")


@pytest.mark.asyncio
async def test_proxy_request_local_model():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"message": {"content": "ok"}}))
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt")
        km._keys = []
        km._healthy_keys = []
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="",
            keys_manager=km,
            client=client,
        )
        body = {"model": "gemma4:26b", "messages": [{"role": "user", "content": "hi"}], "stream": False}
        resp = await prov.proxy_request("api/chat", body, stream=False)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_proxy_request_cloud_strips_suffix():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"message": {"content": "ok"}}))
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt", cloud_base_url="")
        km._keys = ["sk-test"]
        km._healthy_keys = ["sk-test"]
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="https://cloud.example.com",
            keys_manager=km,
            client=client,
        )
        body = {"model": "gemma4:31b-cloud", "messages": [], "stream": False}
        resp = await prov.proxy_request("api/chat", body, stream=False)
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_proxy_request_with_source_override():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt")
        km._keys = []
        km._healthy_keys = []
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="",
            keys_manager=km,
            client=client,
        )
        body = {"model": "gemma4:31b-cloud", "messages": [], "stream": False}
        resp = await prov.proxy_request("api/chat", body, stream=False, source="local")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_proxy_head_local():
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt")
        km._keys = []
        km._healthy_keys = []
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="",
            keys_manager=km,
            client=client,
        )
        resp = await prov.proxy_head("api/blobs/sha256:abc", source="local")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_proxy_raw_local():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["content"] = request.content
        return httpx.Response(201)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt")
        km._keys = []
        km._healthy_keys = []
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="",
            keys_manager=km,
            client=client,
        )
        resp = await prov.proxy_raw("api/blobs/sha256:abc", b"payload", source="local")
        assert resp.status_code == 201
        assert seen["method"] == "POST"
        assert seen["content"] == b"payload"


@pytest.mark.asyncio
async def test_proxy_get_cloud_uses_get_method():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        return httpx.Response(200, json={"models": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        km = KeysManager("secrets/keys.txt", cloud_base_url="")
        km._keys = ["sk-test"]
        km._healthy_keys = ["sk-test"]
        prov = OllamaProvider(
            local_base_url="http://localhost:11434",
            cloud_base_url="https://cloud.example.com",
            keys_manager=km,
            client=client,
        )
        resp = await prov.proxy_get("api/ps", source="cloud")
        assert resp.status_code == 200
        assert seen["method"] == "GET"
