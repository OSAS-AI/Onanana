from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from urllib.parse import urlparse, urlunparse

load_dotenv("secrets/.env")

# api.ollama.com /v1/* 301s to ollama.com (Cloudflare). Prefer the canonical host.
_CLOUD_HOST_ALIASES = {
    "api.ollama.com": "ollama.com",
}


def normalize_cloud_base_url(url: str) -> str:
    """Canonicalize Ollama cloud base URL to avoid Cloudflare 301s on /v1."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme or "https"
    if host in _CLOUD_HOST_ALIASES:
        host = _CLOUD_HOST_ALIASES[host]
        scheme = "https"
    elif host == "ollama.com" and scheme == "http":
        scheme = "https"
    netloc = host
    if parsed.port and not (
        (scheme == "https" and parsed.port == 443)
        or (scheme == "http" and parsed.port == 80)
    ):
        netloc = f"{host}:{parsed.port}"
    return urlunparse((scheme, netloc, parsed.path.rstrip("/"), "", "", ""))


class Settings(BaseSettings):
    warp_host: str = "0.0.0.0"
    warp_port: int = 11435
    local_ollama_base_url: str = "http://localhost:11434"
    cloud_ollama_base_url: str = ""
    cloud_api_key: str = ""
    keys_file_path: str = "secrets/keys.txt"
    lock_file_path: str = "secrets/ollama_keys_lock.txt"
    cloud_model_suffix: str = "-cloud"

    model_config = {"env_prefix": "WARP_", "extra": "ignore"}

    @field_validator("cloud_ollama_base_url", mode="after")
    @classmethod
    def _normalize_cloud_url(cls, v: str) -> str:
        return normalize_cloud_base_url(v)


settings = Settings()
