from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    VALIDATING = "validating"
    DOWNLOADING = "downloading"
    EXTRACTING_AUDIO = "extracting_audio"
    UPLOADING_AUDIO_TO_METIS = "uploading_audio_to_metis"
    TRANSCRIBING = "transcribing"
    AWAITING_REVIEW = "awaiting_review"
    UPLOADING_VIDEO = "uploading_video"
    UPLOADING_CAPTION = "uploading_caption"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.VALIDATING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.VALIDATING: {JobStatus.DOWNLOADING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.DOWNLOADING: {JobStatus.EXTRACTING_AUDIO, JobStatus.AWAITING_REVIEW, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.EXTRACTING_AUDIO: {JobStatus.UPLOADING_AUDIO_TO_METIS, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.UPLOADING_AUDIO_TO_METIS: {JobStatus.TRANSCRIBING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.TRANSCRIBING: {JobStatus.AWAITING_REVIEW, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.AWAITING_REVIEW: {JobStatus.UPLOADING_VIDEO, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.UPLOADING_VIDEO: {JobStatus.UPLOADING_CAPTION, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.UPLOADING_CAPTION: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: {JobStatus.UPLOADING_VIDEO},
    JobStatus.CANCELLED: set(),
}


def can_transition(current: str | JobStatus, target: str | JobStatus) -> bool:
    current_status = JobStatus(current)
    target_status = JobStatus(target)
    return target_status in ALLOWED_TRANSITIONS[current_status]
