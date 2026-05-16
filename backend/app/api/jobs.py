from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db import get_db
from app.jobs.state import JobStatus, can_transition
from app.models import AbuseReport, Job, JobEvent, User, now
from app.schemas import JobCreate, JobEventOut, JobMetadataUpdate, JobOut, ReportCreate, ReportOut, SubtitleUpdate
from app.services.aparat import AparatValidationError, validate_aparat_url
from app.tasks import enqueue_process_job, enqueue_upload_job, process_job, upload_job as run_upload_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

ACTIVE_STATUSES = {
    JobStatus.QUEUED.value,
    JobStatus.VALIDATING.value,
    JobStatus.DOWNLOADING.value,
    JobStatus.EXTRACTING_AUDIO.value,
    JobStatus.UPLOADING_AUDIO_TO_METIS.value,
    JobStatus.TRANSCRIBING.value,
    JobStatus.UPLOADING_VIDEO.value,
    JobStatus.UPLOADING_CAPTION.value,
}


@router.post("", response_model=JobOut)
def create_job(
    payload: JobCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    settings = get_settings()
    if not payload.ownership_confirmed:
        raise HTTPException(status_code=400, detail="Ownership confirmation is required")
    try:
        validate_aparat_url(str(payload.aparat_url))
    except AparatValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _enforce_user_limits(db, user.id, settings.max_jobs_per_user_per_day, settings.max_active_jobs_per_user)

    job = Job(
        user_id=user.id,
        aparat_url=str(payload.aparat_url),
        ownership_confirmed=True,
        language=payload.language or "fa",
        progress_percent=0,
        progress_message="Queued for processing",
    )
    db.add(job)
    db.flush()
    _event(
        db,
        job,
        "job_created",
        "Job created and queued",
        {
            "ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "ownership_confirmed": True,
            "aparat_url": str(payload.aparat_url),
        },
    )
    db.commit()
    db.refresh(job)
    if not enqueue_process_job(job.id):
        background_tasks.add_task(process_job, job.id)
    return _load_job(db, job.id, user.id)


@router.get("", response_model=list[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Job]:
    return list(
        db.scalars(
            select(Job)
            .where(Job.user_id == user.id)
            .order_by(Job.created_at.desc())
            .limit(12)
            .options(selectinload(Job.subtitles), selectinload(Job.events), selectinload(Job.user))
        )
    )


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    return _load_job(db, job_id, user.id)


@router.get("/{job_id}/events", response_model=list[JobEventOut])
def get_events(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[JobEvent]:
    job = _load_job(db, job_id, user.id)
    return list(job.events)


@router.put("/{job_id}/subtitles", response_model=JobOut)
def update_subtitles(
    job_id: str,
    payload: SubtitleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    job = _load_job(db, job_id, user.id)
    if job.status != JobStatus.AWAITING_REVIEW.value:
        raise HTTPException(status_code=409, detail="Subtitles can only be edited during review")

    by_id = {segment.id: segment for segment in job.subtitles}
    for update in payload.segments:
        segment = by_id.get(update.id)
        if not segment:
            raise HTTPException(status_code=404, detail=f"Subtitle segment not found: {update.id}")
        segment.edited_text = update.edited_text
    _event(db, job, "subtitles_updated", "Subtitle text was updated", {"count": len(payload.segments)})
    db.commit()
    return _load_job(db, job.id, user.id)


@router.put("/{job_id}/metadata", response_model=JobOut)
def update_metadata(
    job_id: str,
    payload: JobMetadataUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    job = _load_job(db, job_id, user.id)
    if job.status not in {JobStatus.AWAITING_REVIEW.value, JobStatus.FAILED.value}:
        raise HTTPException(status_code=409, detail="Metadata can only be edited before upload")
    job.title = payload.title
    job.description = payload.description
    _event(db, job, "metadata_updated", "YouTube metadata was updated", None)
    db.commit()
    return _load_job(db, job.id, user.id)


@router.post("/{job_id}/upload", response_model=JobOut)
def upload_job(
    job_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Job:
    job = _load_job(db, job_id, user.id)
    if job.status == JobStatus.FAILED.value and job.error_code == "upload_failed" and job.retryable:
        pass
    elif not can_transition(job.status, JobStatus.UPLOADING_VIDEO):
        raise HTTPException(status_code=409, detail="Job is not ready for upload")
    if not user.youtube_account:
        raise HTTPException(status_code=409, detail="YouTube account is not connected")
    job.status = JobStatus.UPLOADING_VIDEO.value
    job.error_code = None
    job.error_message = None
    job.retryable = False
    job.progress_percent = 82
    job.progress_message = "YouTube upload was queued"
    _event(
        db,
        job,
        "upload_queued",
        "YouTube upload was queued",
        {"ip": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent")},
    )
    db.commit()
    if not enqueue_upload_job(job.id):
        background_tasks.add_task(run_upload_job, job.id)
    return _load_job(db, job.id, user.id)


@router.post("/{job_id}/report", response_model=ReportOut)
def report_job(
    job_id: str,
    payload: ReportCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AbuseReport:
    job = _load_job(db, job_id, user.id)
    report = AbuseReport(
        reporter_user_id=user.id,
        job_id=job.id,
        aparat_url=job.aparat_url,
        youtube_video_url=job.youtube_video_url,
        reason=payload.reason,
        details=payload.details,
        reporter_ip=request.client.host if request.client else None,
    )
    db.add(report)
    _event(
        db,
        job,
        "report_created",
        "User submitted a report",
        {"reason": payload.reason, "ip": request.client.host if request.client else None},
    )
    db.commit()
    db.refresh(report)
    return report


def _load_job(db: Session, job_id: str, user_id: str) -> Job:
    job = db.scalar(
        select(Job)
        .where(Job.id == job_id, Job.user_id == user_id)
        .options(selectinload(Job.subtitles), selectinload(Job.events), selectinload(Job.user))
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _event(db: Session, job: Job, event_type: str, message: str, metadata: dict | None) -> None:
    db.add(JobEvent(job_id=job.id, type=event_type, message=message, event_metadata=metadata))


def _enforce_user_limits(
    db: Session,
    user_id: str,
    max_jobs_per_day: int,
    max_active_jobs: int,
) -> None:
    active_count = db.scalar(
        select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.status.in_(ACTIVE_STATUSES))
    )
    if active_count and active_count >= max_active_jobs:
        raise HTTPException(
            status_code=429,
            detail=f"You already have {active_count} active jobs. Wait for one to finish before starting another.",
        )

    since = now() - timedelta(days=1)
    daily_count = db.scalar(
        select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.created_at >= since)
    )
    if daily_count and daily_count >= max_jobs_per_day:
        raise HTTPException(
            status_code=429,
            detail=f"Daily beta limit reached: {max_jobs_per_day} jobs per user.",
        )
