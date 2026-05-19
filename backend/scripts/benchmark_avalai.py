from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import select

from app.core.config import PROJECT_ROOT, get_settings
from app.db import SessionLocal
from app.models import Artifact, Job
from app.services.aparat import AparatDownloader, extract_video_hash


DEFAULT_URLS = [
    "https://www.aparat.com/v/ugq2z8l",
    "https://www.aparat.com/v/djzvv0o",
    "https://www.aparat.com/v/bit49s2",
    "https://www.aparat.com/v/gtaheo9",
    "https://www.aparat.com/v/htzoeq7",
]

DEFAULT_CASES = [
    ("whisper-1-word", "whisper-1", "verbose_json", "word"),
    ("gpt-4o-mini-json", "gpt-4o-mini-transcribe", "json", None),
    ("groq-large-v3-turbo-json", "groq.whisper-large-v3-turbo", "json", None),
]


@dataclass(frozen=True)
class BenchmarkResult:
    url: str
    video_hash: str
    title: str | None
    duration_seconds: float | None
    audio_seconds: int
    audio_bytes: int
    case: str
    model: str
    response_format: str
    timestamp_granularity: str | None
    ok: bool
    http_status: int | None
    elapsed_seconds: float
    has_word_timestamps: bool
    word_count: int
    segment_count: int
    text_chars: int
    usage: dict[str, Any] | None
    estimated_cost: Any | None
    error: str | None
    text_sample: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark AvalAI STT models on Aparat samples.")
    parser.add_argument("--seconds", type=int, default=75, help="Seconds to trim from each video.")
    parser.add_argument("--include-large-v3", action="store_true", help="Retry groq.whisper-large-v3 too.")
    parser.add_argument("--include-gpt-4o", action="store_true", help="Test gpt-4o-transcribe too.")
    parser.add_argument("--url", action="append", dest="urls", help="Aparat URL. Can be repeated.")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("AVALAI_API_KEY")
    if not api_key:
        raise SystemExit("AVALAI_API_KEY is missing")

    settings = get_settings()
    urls = args.urls or DEFAULT_URLS
    cases = list(DEFAULT_CASES)
    if args.include_gpt_4o:
        cases.append(("gpt-4o-json", "gpt-4o-transcribe", "json", None))
    if args.include_large_v3:
        cases.append(("groq-large-v3-json", "groq.whisper-large-v3", "json", None))

    root = settings.local_artifact_dir / "benchmarks" / time.strftime("%Y%m%d-%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / "avalai-results.json"

    results: list[BenchmarkResult] = []
    for url in urls:
        video_hash = extract_video_hash(url)
        video_dir = root / video_hash
        video_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n=== {video_hash} ===")
        source, title, duration = _source_video_for_url(url, video_dir, settings)
        audio = _make_audio_clip(source, video_dir, min(args.seconds, int(duration or args.seconds)))
        audio_seconds = args.seconds
        audio_bytes = audio.stat().st_size
        print(f"audio={audio_bytes} bytes title={_console(title)}")

        for case_name, model, response_format, granularity in cases:
            result = _run_case(
                api_key=api_key,
                audio_path=audio,
                url=url,
                video_hash=video_hash,
                title=title,
                duration_seconds=duration,
                audio_seconds=audio_seconds,
                audio_bytes=audio_bytes,
                case_name=case_name,
                model=model,
                response_format=response_format,
                granularity=granularity,
            )
            results.append(result)
            print(
                f"{case_name}: ok={result.ok} status={result.http_status} "
                f"elapsed={result.elapsed_seconds:.2f}s words={result.word_count} "
                f"timestamps={result.has_word_timestamps} error={_console(result.error)}"
            )
            output_path.write_text(
                json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print(f"\nWrote {output_path}")


def _source_video_for_url(url: str, output_dir: Path, settings) -> tuple[Path, str | None, float | None]:
    cached = _cached_source_video(url)
    downloader = AparatDownloader(settings.max_video_duration_seconds, settings.max_video_bytes)
    metadata = downloader.inspect(url)
    if cached:
        return cached, metadata.title, float(metadata.duration_seconds) if metadata.duration_seconds else None
    source = downloader.download(url, output_dir)
    return source, metadata.title, float(metadata.duration_seconds) if metadata.duration_seconds else None


def _cached_source_video(url: str) -> Path | None:
    with SessionLocal() as db:
        rows = db.execute(
            select(Artifact, Job)
            .join(Job, Artifact.job_id == Job.id)
            .where(
                Job.aparat_url == url,
                Artifact.kind == "source_video",
                Artifact.deleted_at.is_(None),
            )
            .order_by(Job.updated_at.desc())
        ).all()
    for artifact, _job in rows:
        path = Path(artifact.storage_url)
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            return path
    return None


def _make_audio_clip(source: Path, output_dir: Path, seconds: int) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    audio = output_dir / f"clip-{seconds}s.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-t",
            str(seconds),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "64k",
            str(audio),
        ],
        check=True,
        capture_output=True,
    )
    return audio


def _run_case(
    api_key: str,
    audio_path: Path,
    url: str,
    video_hash: str,
    title: str | None,
    duration_seconds: float | None,
    audio_seconds: int,
    audio_bytes: int,
    case_name: str,
    model: str,
    response_format: str,
    granularity: str | None,
) -> BenchmarkResult:
    form = {
        "model": model,
        "language": "fa",
        "response_format": response_format,
        "temperature": "0",
    }
    if granularity:
        form["timestamp_granularities[]"] = granularity

    started = time.monotonic()
    http_status: int | None = None
    try:
        with audio_path.open("rb") as handle:
            files = {"file": (audio_path.name, handle, "audio/mpeg")}
            with httpx.Client(timeout=240, trust_env=True) as client:
                response = client.post(
                    "https://api.avalai.ir/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=form,
                    files=files,
                )
        elapsed = time.monotonic() - started
        http_status = response.status_code
        if response.status_code >= 400:
            return _failed_result(
                url,
                video_hash,
                title,
                duration_seconds,
                audio_seconds,
                audio_bytes,
                case_name,
                model,
                response_format,
                granularity,
                http_status,
                elapsed,
                response.text,
            )
        data = _response_payload(response)
        text = str(data.get("text") or response.text or "").strip()
        words = data.get("words") if isinstance(data.get("words"), list) else []
        segments = data.get("segments") if isinstance(data.get("segments"), list) else []
        return BenchmarkResult(
            url=url,
            video_hash=video_hash,
            title=title,
            duration_seconds=duration_seconds,
            audio_seconds=audio_seconds,
            audio_bytes=audio_bytes,
            case=case_name,
            model=model,
            response_format=response_format,
            timestamp_granularity=granularity,
            ok=True,
            http_status=http_status,
            elapsed_seconds=round(elapsed, 3),
            has_word_timestamps=bool(words),
            word_count=len(words) or len(text.split()),
            segment_count=len(segments),
            text_chars=len(text),
            usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
            estimated_cost=data.get("estimated_cost"),
            error=None,
            text_sample=text[:600],
        )
    except Exception as exc:
        elapsed = time.monotonic() - started
        return _failed_result(
            url,
            video_hash,
            title,
            duration_seconds,
            audio_seconds,
            audio_bytes,
            case_name,
            model,
            response_format,
            granularity,
            http_status,
            elapsed,
            f"{type(exc).__name__}: {exc}",
        )


def _response_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError:
        return {"text": response.text}
    return parsed if isinstance(parsed, dict) else {"text": str(parsed)}


def _failed_result(
    url: str,
    video_hash: str,
    title: str | None,
    duration_seconds: float | None,
    audio_seconds: int,
    audio_bytes: int,
    case_name: str,
    model: str,
    response_format: str,
    granularity: str | None,
    http_status: int | None,
    elapsed: float,
    error: str,
) -> BenchmarkResult:
    return BenchmarkResult(
        url=url,
        video_hash=video_hash,
        title=title,
        duration_seconds=duration_seconds,
        audio_seconds=audio_seconds,
        audio_bytes=audio_bytes,
        case=case_name,
        model=model,
        response_format=response_format,
        timestamp_granularity=granularity,
        ok=False,
        http_status=http_status,
        elapsed_seconds=round(elapsed, 3),
        has_word_timestamps=False,
        word_count=0,
        segment_count=0,
        text_chars=0,
        usage=None,
        estimated_cost=None,
        error=error[:1200],
        text_sample="",
    )


def _safe(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ")[:120]


def _console(value: object) -> str:
    return _safe(value).encode("unicode_escape").decode()


if __name__ == "__main__":
    main()
