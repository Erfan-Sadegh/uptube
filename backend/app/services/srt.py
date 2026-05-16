import re
from dataclasses import dataclass


SRT_TIME_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


@dataclass(frozen=True)
class SubtitleSegmentData:
    index: int
    start_ms: int
    end_ms: int
    text: str


def parse_timestamp(value: str) -> int:
    hours = int(value[0:2])
    minutes = int(value[3:5])
    seconds = int(value[6:8])
    millis = int(value[9:12])
    return (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis


def format_timestamp(ms: int) -> str:
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_srt(content: str) -> list[SubtitleSegmentData]:
    normalized = content.replace("\r\n", "\n").strip()
    if not normalized:
        return []

    segments: list[SubtitleSegmentData] = []
    for block in re.split(r"\n{2,}", normalized):
        lines = [line.strip("\ufeff") for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            continue
        match = SRT_TIME_RE.match(lines[1])
        if not match:
            continue
        text = "\n".join(lines[2:]).strip()
        segments.append(
            SubtitleSegmentData(
                index=index,
                start_ms=parse_timestamp(match.group("start")),
                end_ms=parse_timestamp(match.group("end")),
                text=text,
            )
        )
    return segments


def render_srt(segments: list[tuple[int, int, int, str]]) -> str:
    blocks = []
    for index, start_ms, end_ms, text in segments:
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}",
                    text.strip(),
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"
