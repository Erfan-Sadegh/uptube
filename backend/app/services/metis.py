import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.retry import with_backoff


class TranscriptionProvider(Protocol):
    def create_generation(
        self,
        audio_url: str,
        language: str,
        response_format: str | None = None,
        prompt: str | None = None,
    ) -> str:
        ...

    def wait_for_srt(self, generation_id: str) -> str:
        ...


class MetisError(RuntimeError):
    pass


@dataclass(frozen=True)
class MetisStatus:
    generation_id: str
    status: str
    percentage: int | None
    srt_content: str | None
    error: Any | None
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class TextTranscription:
    text: str
    duration_seconds: float | None


IN_PROGRESS_STATUSES = {"QUEUE", "WAITING", "RUNNING"}
FAILED_STATUSES = {"ERROR", "CANCELLED"}


def map_metis_status(status: str) -> str:
    normalized = status.upper()
    if normalized in IN_PROGRESS_STATUSES:
        return "transcribing"
    if normalized == "COMPLETED":
        return "completed"
    if normalized in FAILED_STATUSES:
        return "failed"
    return "unknown"


class MetisTranscriptionProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.metisai.ir",
        model: str = "whisper-1",
        poll_interval_seconds: int = 5,
        timeout_seconds: int = 30 * 60,
    ):
        if not api_key:
            raise ValueError("METIS_API_KEY is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.poll_interval_seconds = max(5, poll_interval_seconds)
        self.timeout_seconds = timeout_seconds

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def create_generation(
        self,
        audio_url: str,
        language: str = "fa",
        response_format: str | None = None,
        prompt: str | None = None,
    ) -> str:
        args: dict[str, Any] = {
            "file": audio_url,
            "language": language,
            "temperature": 0,
        }
        if response_format:
            args["response_format"] = response_format
        if prompt:
            args["prompt"] = prompt
        payload = {
            "model": {"name": "openai", "model": self.model},
            "operation": "STT",
            "args": args,
        }
        def send() -> httpx.Response:
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.post(
                    f"{self.base_url}/api/v2/generate",
                    headers=self._headers,
                    json=payload,
                )
            response.raise_for_status()
            return response

        response = with_backoff(send, attempts=3, retryable=(httpx.HTTPError,))
        data = response.json()
        generation_id = data.get("id")
        if not generation_id:
            raise MetisError("Metis create response did not include an id")
        return generation_id

    def poll_once(self, generation_id: str) -> MetisStatus:
        def send() -> httpx.Response:
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.get(
                    f"{self.base_url}/api/v2/generate/{generation_id}",
                    headers=self._headers,
                )
            response.raise_for_status()
            return response

        response = with_backoff(send, attempts=3, retryable=(httpx.HTTPError,))
        data = response.json()
        return MetisStatus(
            generation_id=data.get("id", generation_id),
            status=data.get("status", "UNKNOWN"),
            percentage=data.get("percentage"),
            srt_content=extract_srt_from_metis_response(data),
            error=data.get("error"),
            raw_data=data,
        )

    def wait_for_srt(self, generation_id: str) -> str:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            status = self.poll_once(generation_id)
            mapped = map_metis_status(status.status)
            if mapped == "completed":
                if not status.srt_content:
                    raise MetisError("Metis completed without SRT content")
                return status.srt_content
            if mapped == "failed":
                raise MetisError(f"Metis generation failed: {status.error or status.status}")
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError("Timed out waiting for Metis transcription")

    def wait_for_text(self, generation_id: str) -> TextTranscription:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            status = self.poll_once(generation_id)
            mapped = map_metis_status(status.status)
            if mapped == "completed":
                text_result = extract_text_from_metis_response(status.raw_data)
                if text_result.text:
                    return text_result
                raise MetisError("Metis completed without transcription text")
            if mapped == "failed":
                raise MetisError(f"Metis generation failed: {status.error or status.status}")
            time.sleep(self.poll_interval_seconds)
        raise TimeoutError("Timed out waiting for Metis transcription")


def extract_srt_from_metis_response(data: dict[str, Any]) -> str | None:
    generations = data.get("generations") or []
    if generations:
        first = generations[0] or {}
        content = first.get("content")
        if isinstance(content, str) and "-->" in content:
            return content
        url = first.get("url")
        if isinstance(url, str) and url:
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.get(url)
            response.raise_for_status()
            text = response.text
            if "-->" in text:
                return text

    raw = data.get("rawResponse")
    if isinstance(raw, str) and "-->" in raw:
        return raw
    if isinstance(raw, dict):
        for key in ("text", "srt", "content"):
            value = raw.get(key)
            if isinstance(value, str) and "-->" in value:
                return value
    return None


def extract_text_from_metis_response(data: dict[str, Any]) -> TextTranscription:
    for candidate in _metis_payload_candidates(data):
        text = candidate.get("text")
        if isinstance(text, str):
            duration = candidate.get("duration")
            return TextTranscription(
                text=text.strip(),
                duration_seconds=float(duration) if isinstance(duration, int | float) else None,
            )
    return TextTranscription(text="", duration_seconds=None)


def _metis_payload_candidates(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    raw = data.get("rawResponse")
    if isinstance(raw, dict):
        candidates.append(raw)
    if isinstance(raw, str):
        _append_json_candidate(candidates, raw)

    generations = data.get("generations") or []
    if generations:
        first = generations[0] or {}
        content = first.get("content")
        if isinstance(content, dict):
            candidates.append(content)
        if isinstance(content, str):
            _append_json_candidate(candidates, content)
        url = first.get("url")
        if isinstance(url, str) and url:
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.get(url)
            response.raise_for_status()
            _append_json_candidate(candidates, response.text)
    return candidates


def _append_json_candidate(candidates: list[dict[str, Any]], value: str) -> None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        if value.strip():
            candidates.append({"text": value.strip(), "duration": None})
        return
    if isinstance(parsed, dict):
        candidates.append(parsed)
        nested = parsed.get("rawResponse")
        if isinstance(nested, str):
            _append_json_candidate(candidates, nested)
