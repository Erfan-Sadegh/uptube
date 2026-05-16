from pathlib import Path
import time


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_FORCE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
YOUTUBE_SCOPES = [YOUTUBE_UPLOAD_SCOPE, YOUTUBE_FORCE_SSL_SCOPE]


class YouTubeUploadError(RuntimeError):
    pass


class YouTubeUploader:
    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("YouTube access token is required")
        self.access_token = access_token

    def upload_private_video(self, video_path: Path, title: str, description: str) -> str:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        credentials = Credentials(token=self.access_token)
        youtube = build("youtube", "v3", credentials=credentials)
        body = {
            "snippet": {"title": title, "description": description},
            "status": {"privacyStatus": "private"},
        }
        media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = _execute_resumable(request)
        video_id = response.get("id")
        if not video_id:
            raise YouTubeUploadError("YouTube upload did not return a video id")
        return video_id

    def upload_caption(self, video_id: str, srt_path: Path, language: str = "fa") -> None:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        credentials = Credentials(token=self.access_token)
        youtube = build("youtube", "v3", credentials=credentials)
        body = {
            "snippet": {
                "videoId": video_id,
                "language": language,
                "name": "Generated subtitles",
                "isDraft": False,
            }
        }
        media = MediaFileUpload(str(srt_path), mimetype="application/octet-stream", chunksize=256 * 1024, resumable=True)
        request = youtube.captions().insert(part="snippet", body=body, media_body=media)
        _execute_resumable(request)


def _execute_resumable(request):
    response = None
    retries = 0
    while response is None:
        try:
            _status, response = request.next_chunk()
            retries = 0
        except Exception:
            retries += 1
            if retries > 5:
                raise
            time.sleep(min(2**retries, 30))
    return response
