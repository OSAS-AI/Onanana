from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv("secrets/.env")


class Settings(BaseSettings):
    warp_host: str = "0.0.0.0"
    warp_port: int = 11435
    local_ollama_base_url: str = "http://localhost:11434"
    cloud_ollama_base_url: str = ""
    cloud_api_key: str = ""
    keys_file_path: str = "secrets/keys.txt"
    short_lock_file_path: str = "secrets/ollama_shorttime_keys_lock.txt"
    long_lock_file_path: str = "secrets/ollama_longtime_keys_lock.txt"
    cloud_model_suffix: str = "-cloud"

    model_config = {"env_prefix": "WARP_", "extra": "ignore"}


settings = Settings()
