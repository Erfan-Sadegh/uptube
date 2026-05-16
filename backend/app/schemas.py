from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


class JobCreate(BaseModel):
    aparat_url: HttpUrl = Field(alias="aparatUrl")
    ownership_confirmed: bool = Field(alias="ownershipConfirmed")
    language: str = "fa"
    subtitles_enabled: bool = Field(default=True, alias="subtitlesEnabled")

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if value not in {"fa", "en"}:
            raise ValueError("Language must be fa or en")
        return value


class JobMetadataUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""


class SubtitleSegmentUpdate(BaseModel):
    id: str
    edited_text: str | None = Field(default=None, alias="editedText")


class SubtitleUpdate(BaseModel):
    segments: list[SubtitleSegmentUpdate]


class ReportCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=100)
    details: str | None = Field(default=None, max_length=2000)


class SubtitleSegmentOut(BaseModel):
    id: str
    index: int
    start_ms: int = Field(alias="startMs")
    end_ms: int = Field(alias="endMs")
    text: str
    edited_text: str | None = Field(alias="editedText")

    class Config:
        from_attributes = True
        populate_by_name = True


class JobEventOut(BaseModel):
    id: str
    type: str
    message: str
    event_metadata: dict | None = Field(alias="metadata")
    created_at: datetime = Field(alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class JobOut(BaseModel):
    id: str
    aparat_url: str = Field(alias="aparatUrl")
    status: str
    language: str
    subtitles_enabled: bool = Field(alias="subtitlesEnabled")
    ownership_confirmed: bool = Field(alias="ownershipConfirmed")
    title: str | None
    description: str | None
    youtube_video_url: str | None = Field(alias="youtubeVideoUrl")
    error_code: str | None = Field(alias="errorCode")
    error_message: str | None = Field(alias="errorMessage")
    retryable: bool
    progress_percent: int = Field(alias="progressPercent")
    progress_message: str | None = Field(alias="progressMessage")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    subtitles: list[SubtitleSegmentOut] = []

    class Config:
        from_attributes = True
        populate_by_name = True


class MeOut(BaseModel):
    id: str
    email: str
    youtube_connected: bool = Field(alias="youtubeConnected")
    channel_title: str | None = Field(alias="channelTitle")

    class Config:
        populate_by_name = True


class ReportOut(BaseModel):
    id: str
    reason: str
    created_at: datetime = Field(alias="createdAt")

    class Config:
        from_attributes = True
        populate_by_name = True
