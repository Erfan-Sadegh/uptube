import shutil
from pathlib import Path

import httpx

from app.core.retry import with_backoff


class ArtifactStorage:
    def put_local(self, source: Path, destination_dir: Path, name: str) -> Path:
        destination_dir.mkdir(parents=True, exist_ok=True)
        target = destination_dir / name
        shutil.copy2(source, target)
        return target


class MetisStorageClient:
    def __init__(self, api_key: str, base_url: str = "https://api.metisai.ir"):
        if not api_key:
            raise ValueError("METIS_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def upload(self, file_path: Path) -> str:
        def send() -> httpx.Response:
            with file_path.open("rb") as file:
                files = {"files": (file_path.name, file)}
                response = httpx.post(
                    f"{self.base_url}/api/v1/storage",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    timeout=120,
                    trust_env=False,
                )
            response.raise_for_status()
            return response

        response = with_backoff(send, attempts=3, retryable=(httpx.HTTPError,))
        data = response.json()
        files_data = data.get("files") or []
        if not files_data or not files_data[0].get("url"):
            raise RuntimeError("Metis storage upload did not return a file URL")
        return files_data[0]["url"]
