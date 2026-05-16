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


ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.VALIDATING, JobStatus.FAILED},
    JobStatus.VALIDATING: {JobStatus.DOWNLOADING, JobStatus.FAILED},
    JobStatus.DOWNLOADING: {JobStatus.EXTRACTING_AUDIO, JobStatus.FAILED},
    JobStatus.EXTRACTING_AUDIO: {JobStatus.UPLOADING_AUDIO_TO_METIS, JobStatus.FAILED},
    JobStatus.UPLOADING_AUDIO_TO_METIS: {JobStatus.TRANSCRIBING, JobStatus.FAILED},
    JobStatus.TRANSCRIBING: {JobStatus.AWAITING_REVIEW, JobStatus.FAILED},
    JobStatus.AWAITING_REVIEW: {JobStatus.UPLOADING_VIDEO, JobStatus.FAILED},
    JobStatus.UPLOADING_VIDEO: {JobStatus.UPLOADING_CAPTION, JobStatus.FAILED},
    JobStatus.UPLOADING_CAPTION: {JobStatus.COMPLETED, JobStatus.FAILED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: {JobStatus.UPLOADING_VIDEO},
}


def can_transition(current: str | JobStatus, target: str | JobStatus) -> bool:
    current_status = JobStatus(current)
    target_status = JobStatus(target)
    return target_status in ALLOWED_TRANSITIONS[current_status]
