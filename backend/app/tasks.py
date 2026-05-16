from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import TokenCipher
from app.db import SessionLocal
from app.jobs.state import JobStatus, can_transition
from app.models import Artifact, Job, JobEvent, SubtitleSegment
from app.services.aparat import AparatDownloader
from app.services.artifacts import MetisStorageClient
from app.services.audio import extract_audio, split_audio
from app.services.metis import MetisTranscriptionProvider
from app.services.srt import parse_srt, render_srt
from app.services.youtube import YouTubeUploader


QUEUE_NAME = "uptube-jobs"


def enqueue_process_job(job_id: str) -> bool:
    return _enqueue("app.tasks.process_job", job_id)


def enqueue_upload_job(job_id: str) -> bool:
    return _enqueue("app.tasks.upload_job", job_id)


def _enqueue(func_path: str, job_id: str) -> bool:
    settings = get_settings()
    try:
        from redis import Redis
        from rq import Queue

        queue = Queue(QUEUE_NAME, connection=Redis.from_url(settings.redis_url))
        queue.enqueue(func_path, job_id, job_timeout=60 * 60)
        return True
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
            metadata = downloader.inspect(job.aparat_url)
            job.title = job.title or metadata.title or "Aparat video"
            job.description = job.description or "Uploaded from Aparat with generated subtitles."
            db.commit()

            _transition(db, job, JobStatus.DOWNLOADING, "downloading", "Downloading source video")
            source_video = downloader.download(job.aparat_url, work_dir)
            _artifact(db, job, "source_video", str(source_video))

            _transition(db, job, JobStatus.EXTRACTING_AUDIO, "extracting_audio", "Extracting audio")
            audio_path = extract_audio(source_video, work_dir)

            _transition(
                db,
                job,
                JobStatus.UPLOADING_AUDIO_TO_METIS,
                "metis_storage_uploading",
                "Preparing audio chunks for Metis",
            )
            _artifact(db, job, "audio", str(audio_path))

            _transition(db, job, JobStatus.TRANSCRIBING, "transcribing", "Transcribing audio with Metis")
            provider = MetisTranscriptionProvider(
                settings.metis_api_key,
                poll_interval_seconds=settings.metis_poll_interval_seconds,
                timeout_seconds=settings.metis_timeout_seconds,
            )

            chunks = split_audio(audio_path, work_dir / "chunks")
            metis_storage = MetisStorageClient(settings.metis_api_key)
            srt_rows: list[tuple[int, int, int, str]] = []
            offset_ms = 0
            for index, chunk in enumerate(chunks, start=1):
                audio_url = metis_storage.upload(chunk)
                generation_id = provider.create_generation(audio_url, job.language)
                if index == 1:
                    job.metis_generation_id = generation_id
                db.add(
                    JobEvent(
                        job_id=job.id,
                        type="metis_generation_created",
                        message=f"chunk {index}",
                        event_metadata={"generation_id": generation_id},
                    )
                )
                db.commit()

                text_result = provider.wait_for_text(generation_id)
                duration_ms = int((text_result.duration_seconds or 25) * 1000)
                text = text_result.text.strip()
                if text:
                    srt_rows.append((len(srt_rows) + 1, offset_ms, offset_ms + duration_ms, text))
                offset_ms += duration_ms

            if not srt_rows:
                raise RuntimeError("Metis completed without usable subtitle text")
            srt_content = render_srt(srt_rows)
            srt_path = work_dir / "subtitles.srt"
            srt_path.write_text(srt_content, encoding="utf-8")
            _artifact(db, job, "srt", str(srt_path))
            _replace_subtitles(db, job, srt_content)
            _transition(
                db,
                job,
                JobStatus.AWAITING_REVIEW,
                "awaiting_review",
                "Subtitles are ready for review",
            )
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
            )
            job.youtube_video_id = video_id
            job.youtube_video_url = f"https://www.youtube.com/watch?v={video_id}"
            db.commit()

            _transition(
                db,
                job,
                JobStatus.UPLOADING_CAPTION,
                "uploading_caption",
                "Uploading SRT caption to YouTube",
            )
            uploader.upload_caption(video_id, srt_path, job.language)
            _transition(db, job, JobStatus.COMPLETED, "completed", "Upload completed")
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
    if not can_transition(job.status, target):
        raise RuntimeError(f"Invalid job transition: {job.status} -> {target.value}")
    job.status = target.value
    job.error_code = None
    job.error_message = None
    db.add(JobEvent(job_id=job.id, type=event_type, message=message))
    db.commit()


def _fail(db: Session, job: Job, code: str, message: str, retryable: bool) -> None:
    job.status = JobStatus.FAILED.value
    job.error_code = code
    job.error_message = message
    job.retryable = retryable
    db.add(JobEvent(job_id=job.id, type="failed", message=message, event_metadata={"code": code}))
    db.commit()


def _artifact(db: Session, job: Job, kind: str, storage_url: str) -> None:
    db.add(Artifact(job_id=job.id, kind=kind, storage_url=storage_url))
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
    access_token = response.json().get("access_token")
    if not access_token:
        raise RuntimeError("Google refresh did not return an access token")
    return access_token
