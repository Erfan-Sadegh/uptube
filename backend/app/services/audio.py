import subprocess
import shutil
from pathlib import Path


class AudioExtractionError(RuntimeError):
    pass


def extract_audio(source_video: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / "audio.mp3"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_video),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        "64k",
        str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not audio_path.exists():
        raise AudioExtractionError("FFmpeg failed to extract audio")
    return audio_path


def split_audio(audio_path: Path, output_dir: Path, chunk_seconds: int = 25) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    chunk_template = output_dir / "chunk-%03d.mp3"
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(audio_path),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-reset_timestamps",
        "1",
        "-acodec",
        "libmp3lame",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-b:a",
        "64k",
        str(chunk_template),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    chunks = sorted(output_dir.glob("chunk-*.mp3"))
    if result.returncode != 0 or not chunks:
        raise AudioExtractionError("FFmpeg failed to split audio")
    return chunks
