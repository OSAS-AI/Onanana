import asyncio
import logging
import random
from pathlib import Path
import sys
import httpx

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parents[2]
sys.path.append(str(ROOT_DIR))

class KeysManager:
    def __init__(self, file_path: str, cloud_base_url: str = "",
                 short_lock_path: str = "", long_lock_path: str = ""):
        self._file_path = Path(file_path)
        self._short_lock_path = Path(short_lock_path) if short_lock_path else None
        self._long_lock_path = Path(long_lock_path) if long_lock_path else None
        self._cloud_base = cloud_base_url.rstrip("/")
        self._keys: list[str] = []
        self._locked_keys: set[str] = set()
        self._index: int = 0
        self._lock = asyncio.Lock()
        # Increased timeout slightly to accommodate chat API response time
        self._client = httpx.AsyncClient(timeout=15.0)
        self._healthy_keys: list[str] = []

    def _load_locked_keys(self) -> set[str]:
        locked: set[str] = set()
        for path in (self._short_lock_path, self._long_lock_path):
            if path and path.exists():
                keys = [
                    line.strip()
                    for line in path.read_text().splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                if keys:
                    logger.info("Loaded %d locked key(s) from %s", len(keys), path)
                locked.update(keys)
        return locked

    def load_keys(self) -> list[str]:
        if not self._file_path.exists():
            logger.warning("Keys file not found: %s", self._file_path)
            return []
        keys = [
            line.strip()
            for line in self._file_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self._locked_keys = self._load_locked_keys()
        if self._locked_keys:
            keys = [k for k in keys if k not in self._locked_keys]
            logger.info("Filtered out %d locked key(s)", len(self._locked_keys))
        self._keys = keys
        self._healthy_keys = list(keys)
        logger.info("Loaded %d key(s) from %s", len(keys), self._file_path)
        return keys

    async def check_key_health(self, key: str) -> bool:
        if not self._cloud_base:
            return True
        try:
            url = f"{self._cloud_base}/api/chat"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}"
            }
            # Query request matching the Ollama chat API structure
            payload = {
                "model": "gemma3:4b-cloud",
                "messages": [
                    {
                        "role": "user",
                        "content": "test"
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.7
                }
            }
            r = await self._client.post(url, headers=headers, json=payload)
            # Consider healthy only if response code is exactly 200
            return r.status_code == 200
        except Exception as e:
            logger.debug("Health check failed for key: %s", e)
            return False

    async def refresh_healthy_keys(self) -> list[str]:
        self._locked_keys = self._load_locked_keys()
        healthy = []
        for key in self._keys:
            if key in self._locked_keys:
                continue
            if await self.check_key_health(key):
                healthy.append(key)
        async with self._lock:
            self._healthy_keys = healthy
            if self._index >= len(self._healthy_keys):
                self._index = 0
        logger.info("Healthy keys: %d / %d", len(healthy), len(self._keys))
        return healthy

    async def get_next_healthy_key(self) -> str | None:
        async with self._lock:
            if self._healthy_keys:
                key = self._healthy_keys[self._index % len(self._healthy_keys)]
                self._index = (self._index + 1) % len(self._healthy_keys)
                return key

        await self.refresh_healthy_keys()

        async with self._lock:
            if self._healthy_keys:
                key = self._healthy_keys[self._index % len(self._healthy_keys)]
                self._index = (self._index + 1) % len(self._healthy_keys)
                return key
            return None

    async def close(self):
        await self._client.aclose()


if __name__ == "__main__":
    # Configure logging for the main execution block
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    async def main():
        # Initialize with the paths and URLs from your configuration
        manager = KeysManager(
            file_path="secrets/keys.txt",
            cloud_base_url="https://api.ollama.com"  # Change to your actual cloud endpoint if different
        )
        
        keys = manager.load_keys()
        if not keys:
            logger.warning("No keys loaded. Exiting.")
            await manager.close()
            return
            
        logger.info("Checking health of keys via Ollama chat API (gemma3:4b-cloud)...")
        healthy_keys = await manager.refresh_healthy_keys()
        
        if healthy_keys:
            # Randomly release/select a healthy key
            selected_key = random.choice(healthy_keys)
            logger.info(f"Successfully found {len(healthy_keys)} healthy key(s).")
            logger.info(f"Randomly selected healthy key: {selected_key}")
        else:
            logger.warning("No healthy keys found. Please check your keys.txt or cloud endpoint.")
            
        await manager.close()

    asyncio.run(main())