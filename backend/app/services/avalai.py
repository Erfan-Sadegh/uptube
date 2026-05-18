from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.retry import with_backoff


class AvalAIError(RuntimeError):
    pass


@dataclass(frozen=True)
class AvalAIWord:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class AvalAITranscription:
    text: str
    duration_seconds: float | None
    words: list[AvalAIWord]
    usage: dict[str, Any] | None


class AvalAITranscriptionProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.avalai.ir/v1",
        model: str = "whisper-1",
        timeout_seconds: int = 30 * 60,
    ):
        if not api_key:
            raise ValueError("AVALAI_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def transcribe_verbose_words(self, audio_path: Path, language: str) -> AvalAITranscription:
        form = {
            "model": self.model,
            "language": language,
            "response_format": "verbose_json",
            "temperature": "0",
            "timestamp_granularities[]": "word",
        }

        def send() -> httpx.Response:
            with audio_path.open("rb") as handle:
                files = {"file": (audio_path.name, handle, _content_type(audio_path))}
                with httpx.Client(timeout=self.timeout_seconds, trust_env=True) as client:
                    response = client.post(
                        f"{self.base_url}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        data=form,
                        files=files,
                    )
            if response.status_code >= 500:
                response.raise_for_status()
            if response.status_code >= 400:
                raise AvalAIError(_safe_error_message(response))
            return response

        response = with_backoff(send, attempts=3, retryable=(httpx.HTTPError,))
        data = response.json()
        return AvalAITranscription(
            text=str(data.get("text") or "").strip(),
            duration_seconds=_float_or_none(data.get("duration")),
            words=_parse_words(data.get("words")),
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
        )


def _parse_words(value: Any) -> list[AvalAIWord]:
    if not isinstance(value, list):
        return []
    words: list[AvalAIWord] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("word") or item.get("text") or "").strip()
        start = _float_or_none(item.get("start"))
        end = _float_or_none(item.get("end"))
        if not text or start is None or end is None:
            continue
        start_ms = max(0, int(start * 1000))
        end_ms = max(start_ms + 1, int(end * 1000))
        words.append(AvalAIWord(start_ms=start_ms, end_ms=end_ms, text=text))
    return words


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "video/mp4",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".flac": "audio/flac",
    }.get(suffix, "application/octet-stream")


def _safe_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"AvalAI request failed with HTTP {response.status_code}"
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        if message:
            return f"AvalAI request failed: {message}"
    return f"AvalAI request failed with HTTP {response.status_code}"
