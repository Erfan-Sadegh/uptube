import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.retry import with_backoff
from app.core.security import TokenCipher
from app.db import SessionLocal
from app.jobs.state import JobStatus, can_transition
from app.models import Artifact, Job, JobEvent, SubtitleSegment, now
from app.services.aparat import AparatDownloader, AparatValidationError
from app.services.artifacts import MetisStorageClient
from app.services.audio import extract_audio, media_duration_seconds, split_audio
from app.services.metis import MetisTranscriptionProvider
from app.services.srt import parse_srt, render_srt
from app.services.youtube import YouTubeUploader


QUEUE_NAME = "uptube-jobs"
MIYANDAR_CREDIT = "Made with miyandar ♥"


@dataclass(frozen=True)
class ChunkTranscription:
    index: int
    generation_id: str
    text: str
    duration_ms: int


class JobCancelled(RuntimeError):
    pass


def _default_youtube_description(subtitles_enabled: bool) -> str:
    base = "Uploaded from Aparat with generated subtitles." if subtitles_enabled else "Uploaded from Aparat."
    return f"{base}\n\n{MIYANDAR_CREDIT}"


def enqueue_process_job(job_id: str) -> bool:
    return _enqueue("app.tasks.process_job", job_id)


def enqueue_upload_job(job_id: str) -> bool:
    return _enqueue("app.tasks.upload_job", job_id)


def _enqueue(func_path: str, job_id: str) -> bool:
    settings = get_settings()
    try:
        from redis import Redis
        from rq import Queue

        connection = Redis.from_url(settings.redis_url)
        if not _has_active_worker(connection):
            return False
        queue = Queue(QUEUE_NAME, connection=connection)
        queue.enqueue(func_path, job_id, job_timeout=60 * 60)
        return True
    except Exception:
        return False


def _has_active_worker(connection) -> bool:
    try:
        from rq import Worker

        return bool(Worker.all(connection=connection))
    except Exception:
        return False


def process_job(job_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        job = _get_job(db, job_id)
        work_dir = settings.local_artifact_dir / job.id
        try:
            _transition(db, job, JobStatus.VALIDATING, "validating", "Validating Aparat URL")
            downloader = AparatDownloader(
                settings.max_video_duration_seconds,
                settings.max_video_bytes,
            )
            metadata = _retry_aparat_step(
                db,
                job,
                lambda: downloader.inspect(job.aparat_url),
                "Aparat did not respond while reading the video",
            )
            _ensure_not_cancelled(db, job)
            job.title = job.title or metadata.title or "Aparat video"
            job.description = job.description or _default_youtube_description(job.subtitles_enabled)
            db.commit()

            _transition(db, job, JobStatus.DOWNLOADING, "downloading", "Downloading source video")
            source_video = _retry_aparat_step(
                db,
                job,
                lambda: downloader.download(job.aparat_url, work_dir),
                "Aparat did not respond while downloading the video",
            )
            _ensure_not_cancelled(db, job)
            _artifact(db, job, "source_video", str(source_video))

            if not job.subtitles_enabled:
                _transition(
                    db,
                    job,
                    JobStatus.AWAITING_REVIEW,
                    "awaiting_review",
                    "Video is ready to publish",
                )
                return

            _transition(db, job, JobStatus.EXTRACTING_AUDIO, "extracting_audio", "Extracting audio")
            audio_path = extract_audio(source_video, work_dir)
            _ensure_not_cancelled(db, job)

            _transition(
                db,
                job,
                JobStatus.UPLOADING_AUDIO_TO_METIS,
                "metis_storage_uploading",
                "Preparing audio chunks for Metis",
            )
            _artifact(db, job, "audio", str(audio_path))

            _transition(db, job, JobStatus.TRANSCRIBING, "transcribing", "Transcribing audio with Metis")

            chunks = split_audio(audio_path, work_dir / "chunks", chunk_seconds=settings.audio_chunk_seconds)
            _event(
                db,
                job,
                "audio_chunked",
                f"Audio split into {len(chunks)} chunks",
                {"count": len(chunks), "parallelism": settings.metis_parallel_chunks},
            )
            _set_progress(db, job, 42, f"Audio split into {len(chunks)} chunks")

            results: dict[int, ChunkTranscription] = {}
            completed = 0
            max_workers = max(1, min(settings.metis_parallel_chunks, len(chunks)))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _transcribe_chunk,
                        index,
                        chunk,
                        job.language,
                        settings.metis_api_key,
                        settings.metis_poll_interval_seconds,
                        settings.metis_timeout_seconds,
                        settings.audio_chunk_seconds,
                    ): index
                    for index, chunk in enumerate(chunks, start=1)
                }
                for future in as_completed(futures):
                    result = future.result()
                    _ensure_not_cancelled(db, job)
                    results[result.index] = result
                    completed += 1
                    if result.index == 1 or not job.metis_generation_id:
                        job.metis_generation_id = result.generation_id
                    _event(
                        db,
                        job,
                        "metis_chunk_completed",
                        f"Transcribed chunk {completed} of {len(chunks)}",
                        {"generation_id": result.generation_id, "chunk_index": result.index},
                    )
                    percent = 45 + int((completed / len(chunks)) * 35)
                    _set_progress(db, job, percent, f"Transcribed {completed} of {len(chunks)} audio chunks")

            srt_rows: list[tuple[int, int, int, str]] = []
            offset_ms = 0
            for index in sorted(results):
                result = results[index]
                if result.text:
                    srt_rows.append((len(srt_rows) + 1, offset_ms, offset_ms + result.duration_ms, result.text))
                offset_ms += result.duration_ms

            if not srt_rows:
                raise RuntimeError("Metis completed without usable subtitle text")
            srt_content = render_srt(srt_rows)
            srt_path = work_dir / "subtitles.srt"
            srt_path.write_text(srt_content, encoding="utf-8")
            _artifact(db, job, "srt", str(srt_path))
            _replace_subtitles(db, job, srt_content)
            _delete_artifact_kind(db, job, "audio", "Audio cleaned after transcription")
            _delete_path(work_dir / "chunks")
            _transition(
                db,
                job,
                JobStatus.AWAITING_REVIEW,
                "awaiting_review",
                "Subtitles are ready for review",
            )
        except JobCancelled:
            return
        except Exception as exc:
            _fail(db, job, "processing_failed", str(exc), retryable=True)


def upload_job(job_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as db:
        job = _get_job(db, job_id)
        try:
            db.refresh(job, attribute_names=["user", "artifacts", "subtitles"])
            if not job.user.youtube_account:
                raise RuntimeError("YouTube account is not connected")

            source_video = _artifact_path(job, "source_video")
            if not source_video:
                raise RuntimeError("Source video artifact is missing")

            srt_path = settings.local_artifact_dir / job.id / "final-subtitles.srt"
            srt_path.write_text(_render_job_srt(job), encoding="utf-8")

            access_token = _refresh_youtube_access_token(job.user.youtube_account.encrypted_refresh_token)
            uploader = YouTubeUploader(access_token)
            if job.status != JobStatus.UPLOADING_VIDEO.value:
                _transition(
                    db,
                    job,
                    JobStatus.UPLOADING_VIDEO,
                    "uploading_video",
                    "Uploading private video to YouTube",
                )
            else:
                db.add(JobEvent(job_id=job.id, type="uploading_video", message="Uploading private video to YouTube"))
                db.commit()
            video_id = uploader.upload_private_video(
                Path(source_video),
                job.title or "Aparat video",
                job.description or "",
                on_progress=lambda percent: _set_progress(
                    db,
                    job,
                    82 + int(percent * 0.13),
                    f"Uploading video to YouTube ({percent}%)",
                ),
            )
            job.youtube_video_id = video_id
            job.youtube_video_url = f"https://www.youtube.com/watch?v={video_id}"
            db.commit()
            _ensure_not_cancelled(db, job)

            if not job.subtitles_enabled or not job.subtitles:
                _transition(db, job, JobStatus.COMPLETED, "completed", "Upload completed")
                _delete_artifact_kind(db, job, "source_video", "Source video cleaned after completion")
                return

            _transition(
                db,
                job,
                JobStatus.UPLOADING_CAPTION,
                "uploading_caption",
                "Uploading SRT caption to YouTube",
            )
            uploader.upload_caption(
                video_id,
                srt_path,
                job.language,
                on_progress=lambda percent: _set_progress(
                    db,
                    job,
                    95 + int(percent * 0.04),
                    f"Attaching subtitles ({percent}%)",
                ),
            )
            _transition(db, job, JobStatus.COMPLETED, "completed", "Upload completed")
            _delete_artifact_kind(db, job, "source_video", "Source video cleaned after completion")
        except JobCancelled:
            return
        except Exception as exc:
            _fail(db, job, "upload_failed", str(exc), retryable=True)


def _get_job(db: Session, job_id: str) -> Job:
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id)
        .options(selectinload(Job.artifacts), selectinload(Job.subtitles), selectinload(Job.user))
    )
    if not job:
        raise RuntimeError(f"Job not found: {job_id}")
    return job


def _transition(
    db: Session,
    job: Job,
    target: JobStatus,
    event_type: str,
    message: str,
) -> None:
    _ensure_not_cancelled(db, job)
    if not can_transition(job.status, target):
        raise RuntimeError(f"Invalid job transition: {job.status} -> {target.value}")
    job.status = target.value
    job.error_code = None
    job.error_message = None
    job.retryable = False
    job.progress_percent = _default_progress(target)
    job.progress_message = message
    db.add(JobEvent(job_id=job.id, type=event_type, message=message))
    db.commit()


def _set_progress(db: Session, job: Job, percent: int, message: str) -> None:
    db.refresh(job)
    if job.status == JobStatus.CANCELLED.value:
        raise JobCancelled()
    job.progress_percent = max(0, min(100, percent))
    job.progress_message = message
    db.commit()


def _fail(db: Session, job: Job, code: str, message: str, retryable: bool) -> None:
    user_message = _friendly_error(code, message)
    job.status = JobStatus.FAILED.value
    job.error_code = code
    job.error_message = user_message
    job.retryable = retryable
    job.progress_message = user_message
    db.add(
        JobEvent(
            job_id=job.id,
            type="failed",
            message=user_message,
            event_metadata={"code": code, "technical_message": message},
        )
    )
    db.commit()


def _artifact(db: Session, job: Job, kind: str, storage_url: str) -> None:
    settings = get_settings()
    db.add(
        Artifact(
            job_id=job.id,
            kind=kind,
            storage_url=storage_url,
            expires_at=now() + timedelta(hours=settings.artifact_retention_hours),
        )
    )
    db.add(JobEvent(job_id=job.id, type="artifact_created", message=kind))
    db.commit()
    db.refresh(job, attribute_names=["artifacts"])


def _artifact_path(job: Job, kind: str) -> str | None:
    for artifact in job.artifacts:
        if artifact.kind == kind and not artifact.deleted_at:
            return artifact.storage_url
    return None


def _replace_subtitles(db: Session, job: Job, srt_content: str) -> None:
    for segment in list(job.subtitles):
        db.delete(segment)
    for parsed in parse_srt(srt_content):
        db.add(
            SubtitleSegment(
                job_id=job.id,
                index=parsed.index,
                start_ms=parsed.start_ms,
                end_ms=parsed.end_ms,
                text=parsed.text,
            )
        )
    db.add(JobEvent(job_id=job.id, type="subtitles_created", message="SRT parsed into segments"))
    db.commit()
    db.refresh(job, attribute_names=["subtitles"])


def _render_job_srt(job: Job) -> str:
    rows = [
        (
            segment.index,
            segment.start_ms,
            segment.end_ms,
            segment.edited_text if segment.edited_text is not None else segment.text,
        )
        for segment in sorted(job.subtitles, key=lambda item: item.index)
    ]
    return render_srt(rows)


def _refresh_youtube_access_token(encrypted_refresh_token: str) -> str:
    settings = get_settings()
    refresh_token = TokenCipher(settings.token_encryption_key).decrypt(encrypted_refresh_token)

    def send() -> httpx.Response:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response

    response = with_backoff(send, attempts=3, retryable=(httpx.HTTPError,))
    access_token = response.json().get("access_token")
    if not access_token:
        raise RuntimeError("Google refresh did not return an access token")
    return access_token


def _transcribe_chunk(
    index: int,
    chunk: Path,
    language: str,
    api_key: str,
    poll_interval_seconds: int,
    timeout_seconds: int,
    fallback_chunk_seconds: int,
) -> ChunkTranscription:
    measured_duration = media_duration_seconds(chunk)
    audio_url = MetisStorageClient(api_key).upload(chunk)
    provider = MetisTranscriptionProvider(
        api_key,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
    )
    generation_id = provider.create_generation(audio_url, language)
    text_result = provider.wait_for_text(generation_id)
    duration_ms = int((text_result.duration_seconds or measured_duration or fallback_chunk_seconds) * 1000)
    return ChunkTranscription(
        index=index,
        generation_id=generation_id,
        text=text_result.text.strip(),
        duration_ms=duration_ms,
    )


def _event(db: Session, job: Job, event_type: str, message: str, metadata: dict | None) -> None:
    db.add(JobEvent(job_id=job.id, type=event_type, message=message, event_metadata=metadata))
    db.commit()


def _default_progress(target: JobStatus) -> int:
    return {
        JobStatus.QUEUED: 0,
        JobStatus.VALIDATING: 5,
        JobStatus.DOWNLOADING: 12,
        JobStatus.EXTRACTING_AUDIO: 28,
        JobStatus.UPLOADING_AUDIO_TO_METIS: 36,
        JobStatus.TRANSCRIBING: 40,
        JobStatus.AWAITING_REVIEW: 80,
        JobStatus.UPLOADING_VIDEO: 82,
        JobStatus.UPLOADING_CAPTION: 95,
        JobStatus.COMPLETED: 100,
        JobStatus.FAILED: 0,
        JobStatus.CANCELLED: 0,
    }[target]


def _friendly_error(code: str, message: str) -> str:
    lowered = message.lower()
    if "duration exceeds" in lowered:
        return "This video is longer than the current beta limit."
    if "size exceeds" in lowered:
        return "This video is larger than the current beta limit."
    if "aparat video could not be inspected" in lowered:
        return "We could not read this Aparat video. Check that the link is public and try again."
    if "aparat video could not be downloaded" in lowered:
        return "We could not download this Aparat video. The source may be private or temporarily unavailable."
    if "metis" in lowered:
        return "Subtitle generation failed while contacting Metis. This is retryable."
    if "youtube account is not connected" in lowered:
        return "Connect YouTube before uploading."
    if code == "upload_failed":
        return "YouTube upload failed. You can retry the upload from this step."
    return "Processing failed. Please try again."


def _retry_aparat_step(db: Session, job: Job, operation, retry_message: str):
    attempts = 5
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        _ensure_not_cancelled(db, job)
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if not _is_retryable_aparat_error(exc) or attempt == attempts:
                raise
            delay = min(5 * attempt, 20)
            message = f"{retry_message}. Retrying in {delay}s ({attempt}/{attempts - 1})."
            job.progress_message = message
            db.add(
                JobEvent(
                    job_id=job.id,
                    type="aparat_retrying",
                    message=message,
                    event_metadata={"attempt": attempt, "technical_message": str(exc)},
                )
            )
            db.commit()
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def _is_retryable_aparat_error(error: Exception) -> bool:
    if isinstance(error, AparatValidationError):
        message = str(error).lower()
        if "duration exceeds" in message or "size exceeds" in message or "must use http" in message:
            return False
        return True
    message = str(error).lower()
    retry_markers = ("504", "gateway timeout", "timeout", "temporarily", "server error", "expected string or bytes")
    return any(marker in message for marker in retry_markers)


def _ensure_not_cancelled(db: Session, job: Job) -> None:
    db.refresh(job)
    if job.status == JobStatus.CANCELLED.value:
        raise JobCancelled()


def _delete_artifact_kind(db: Session, job: Job, kind: str, message: str) -> None:
    changed = False
    for artifact in job.artifacts:
        if artifact.kind == kind and not artifact.deleted_at:
            _delete_path(Path(artifact.storage_url))
            artifact.deleted_at = now()
            changed = True
    if changed:
        db.add(JobEvent(job_id=job.id, type="artifact_deleted", message=message, event_metadata={"kind": kind}))
        db.commit()


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)


def cleanup_expired_artifacts() -> int:
    deleted = 0
    with SessionLocal() as db:
        artifacts = db.scalars(
            select(Artifact).where(Artifact.deleted_at.is_(None), Artifact.expires_at <= now())
        ).all()
        for artifact in artifacts:
            _delete_path(Path(artifact.storage_url))
            artifact.deleted_at = now()
            deleted += 1
        if deleted:
            db.commit()
    return deleted
