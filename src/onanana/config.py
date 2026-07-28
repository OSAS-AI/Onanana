from pathlib import Path

import yaml
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv("secrets/.env")


def load_ollama_errors() -> dict[int, dict[str, str]]:
    path = Path("configs/ollama_error.yml")
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    raw = (data or {}).get("ollama_cloud_errors", {})
    return {int(k): v for k, v in raw.items()}


class Settings(BaseSettings):
    warp_host: str = "0.0.0.0"
    warp_port: int = 11435
    local_ollama_base_url: str = "http://localhost:11434"
    cloud_ollama_base_url: str = ""
    cloud_api_key: str = ""
    keys_file_path: str = "secrets/keys.txt"
    lock_file_path: str = "secrets/ollama_keys_lock.txt"
    cloud_model_suffix: str = "-cloud"
    ollama_cloud_errors: dict[int, dict[str, str]] = {}

    model_config = {"env_prefix": "WARP_", "extra": "ignore"}


settings = Settings(ollama_cloud_errors=load_ollama_errors())
