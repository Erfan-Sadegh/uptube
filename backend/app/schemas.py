from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class JobCreate(BaseModel):
    aparat_url: HttpUrl = Field(alias="aparatUrl")
    ownership_confirmed: bool = Field(alias="ownershipConfirmed")
    language: str = "fa"


class JobMetadataUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""


class SubtitleSegmentUpdate(BaseModel):
    id: str
    edited_text: str | None = Field(default=None, alias="editedText")


class SubtitleUpdate(BaseModel):
    segments: list[SubtitleSegmentUpdate]


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
    ownership_confirmed: bool = Field(alias="ownershipConfirmed")
    title: str | None
    description: str | None
    youtube_video_url: str | None = Field(alias="youtubeVideoUrl")
    error_code: str | None = Field(alias="errorCode")
    error_message: str | None = Field(alias="errorMessage")
    retryable: bool
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
