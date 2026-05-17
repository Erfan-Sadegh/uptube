from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx


class AparatValidationError(ValueError):
    pass


ALLOWED_HOSTS = {"aparat.com", "www.aparat.com"}


@dataclass(frozen=True)
class AparatMetadata:
    title: str | None
    duration_seconds: int | None
    filesize_bytes: int | None
    direct_video_url: str | None = None


def validate_aparat_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    host = parsed.netloc.lower()
    if parsed.scheme not in {"http", "https"}:
        raise AparatValidationError("Aparat URL must use http or https")
    if host not in ALLOWED_HOSTS:
        raise AparatValidationError("Only aparat.com links are supported")
    if not parsed.path or parsed.path == "/":
        raise AparatValidationError("Aparat URL must point to a video page")
    return raw_url


def extract_video_hash(raw_url: str) -> str:
    validate_aparat_url(raw_url)
    parts = [part for part in urlparse(raw_url).path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "v":
        return parts[1]
    if len(parts) >= 1:
        return parts[-1]
    raise AparatValidationError("Aparat video hash was not found")


class AparatDownloader:
    """Thin yt-dlp adapter. The real binary/network work is isolated here."""

    def __init__(self, max_duration_seconds: int, max_video_bytes: int):
        self.max_duration_seconds = max_duration_seconds
        self.max_video_bytes = max_video_bytes

    def inspect(self, url: str) -> AparatMetadata:
        import yt_dlp

        validate_aparat_url(url)
        api_error: Exception | None = None
        try:
            return self._inspect_via_api(url)
        except Exception as exc:
            api_error = exc

        try:
            with yt_dlp.YoutubeDL(_yt_dlp_options({"skip_download": True})) as ydl:
                info = ydl.extract_info(url, download=False)

            duration = info.get("duration")
            filesize = info.get("filesize") or info.get("filesize_approx")
            self._enforce_limits(duration, filesize)
            return AparatMetadata(
                title=info.get("title"),
                duration_seconds=int(duration) if duration else None,
                filesize_bytes=int(filesize) if filesize else None,
            )
        except Exception as exc:
            detail = f"API error: {api_error}; yt-dlp error: {exc}" if api_error else str(exc)
            raise AparatValidationError(f"Aparat video could not be inspected ({detail})") from exc

    def download(self, url: str, output_dir: Path) -> Path:
        import yt_dlp

        validate_aparat_url(url)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / "source.%(ext)s")
        api_error: Exception | None = None
        try:
            metadata = self._inspect_via_api(url)
            if metadata.direct_video_url:
                return self._download_direct(metadata.direct_video_url, output_dir)
        except Exception as exc:
            api_error = exc

        try:
            with yt_dlp.YoutubeDL(_yt_dlp_options({"outtmpl": output_template})) as ydl:
                info = ydl.extract_info(url, download=True)
                duration = info.get("duration")
                filesize = info.get("filesize") or info.get("filesize_approx")
                self._enforce_limits(duration, filesize)
                downloaded = Path(ydl.prepare_filename(info))

            if not downloaded.exists():
                raise FileNotFoundError("Downloaded source video was not found")
            return downloaded
        except Exception as exc:
            detail = f"API error: {api_error}; yt-dlp error: {exc}" if api_error else str(exc)
            raise AparatValidationError(f"Aparat video could not be downloaded ({detail})") from exc

    def _enforce_limits(self, duration: int | None, filesize: int | None) -> None:
        if duration and duration > self.max_duration_seconds:
            raise AparatValidationError("Video duration exceeds beta limit")
        if filesize and filesize > self.max_video_bytes:
            raise AparatValidationError("Video size exceeds beta limit")

    def _inspect_via_api(self, url: str) -> AparatMetadata:
        video_hash = extract_video_hash(url)
        api_url = f"https://www.aparat.com/etc/api/video/videohash/{video_hash}"
        response = httpx.get(api_url, headers=_headers(), timeout=45, trust_env=False)
        response.raise_for_status()
        video = response.json().get("video")
        if not isinstance(video, dict):
            raise AparatValidationError("Aparat API did not return video data")
        duration = _as_int(video.get("duration"))
        filesize = _as_int(video.get("size"))
        direct_video_url = _select_direct_video_url(video)
        self._enforce_limits(duration, filesize)
        return AparatMetadata(
            title=video.get("title"),
            duration_seconds=duration,
            filesize_bytes=filesize,
            direct_video_url=direct_video_url,
        )

    def _download_direct(self, video_url: str, output_dir: Path) -> Path:
        target = output_dir / "source.mp4"
        with httpx.stream(
            "GET",
            video_url,
            headers=_headers(),
            timeout=180,
            follow_redirects=True,
            trust_env=False,
        ) as response:
            response.raise_for_status()
            content_length = _as_int(response.headers.get("content-length"))
            self._enforce_limits(None, content_length)
            with target.open("wb") as file:
                downloaded = 0
                for chunk in response.iter_bytes():
                    downloaded += len(chunk)
                    if downloaded > self.max_video_bytes:
                        raise AparatValidationError("Video size exceeds beta limit")
                    file.write(chunk)
        if not target.exists() or target.stat().st_size == 0:
            raise FileNotFoundError("Downloaded source video was empty")
        return target


def _select_direct_video_url(video: dict) -> str | None:
    links = video.get("file_link_all")
    if isinstance(links, list):
        ranked = sorted(links, key=lambda item: _profile_rank(item.get("profile")), reverse=True)
        for item in ranked:
            urls = item.get("urls")
            if isinstance(urls, list) and urls and isinstance(urls[0], str):
                return urls[0]
    file_link = video.get("file_link")
    return file_link if isinstance(file_link, str) else None


def _profile_rank(profile: object) -> int:
    if not isinstance(profile, str):
        return 0
    digits = "".join(char for char in profile if char.isdigit())
    return int(digits) if digits else 0


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        return int(digits) if digits else None
    return None


def _headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0 Safari/537.36"
        )
    }


def _yt_dlp_options(extra: dict) -> dict:
    options = {
        "quiet": True,
        "proxy": "",
        "socket_timeout": 45,
        "retries": 3,
        "extractor_retries": 3,
        "http_headers": _headers(),
    }
    options.update(extra)
    return options
