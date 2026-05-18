import re
import unicodedata
from collections import Counter
from math import ceil


_CONTROL_WHITESPACE_RE = re.compile(r"\s+")
_REPEATED_LETTER_RE = re.compile(r"([^\W\d_])\1{4,}", re.UNICODE)
_REPEATED_PUNCTUATION_RE = re.compile(r"([!?.؟،,؛:])\1{2,}")
_REPEATED_WORD_RE = re.compile(r"\b([^\W\d_]{2,})(?:\s+\1){3,}\b", re.IGNORECASE | re.UNICODE)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_MAX_SUBTITLE_SEGMENT_MS = 7_000
_MAX_SUBTITLE_WORDS = 14
_INSTRUCTION_ECHO_MARKERS = (
    "\u062a\u0631\u062c\u0645\u0647 \u0646\u06a9\u0646",
    "\u0645\u0648\u0633\u06cc\u0642\u06cc\u060c \u0633\u06a9\u0648\u062a \u0648 \u0622\u0648\u0627\u0647\u0627\u06cc \u0646\u0627\u0645\u0641\u0647\u0648\u0645",
    "\u0627\u0635\u0637\u0644\u0627\u062d\u0627\u062a \u062a\u062e\u0635\u0635\u06cc",
    "transcribe only clear spoken",
    "do not translate",
    "do not invent missing words",
)

_PERSIAN_REPLACEMENTS = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
    }
)


def clean_transcript_text(text: str, language: str = "fa") -> str:
    normalized = _normalize_text(text, language)
    if not normalized:
        return ""
    if _looks_like_instruction_echo(normalized):
        return ""
    if _looks_like_repeated_noise(normalized):
        return ""

    normalized = _REPEATED_LETTER_RE.sub(r"\1\1\1", normalized)
    normalized = _REPEATED_PUNCTUATION_RE.sub(r"\1", normalized)
    normalized = _REPEATED_WORD_RE.sub(lambda match: " ".join([match.group(1)] * 2), normalized)
    normalized = _CONTROL_WHITESPACE_RE.sub(" ", normalized).strip()

    if _looks_like_repeated_noise(normalized):
        return ""
    return normalized


def split_text_for_subtitle_rows(text: str, start_ms: int, end_ms: int) -> list[tuple[int, int, str]]:
    duration_ms = max(1, end_ms - start_ms)
    words = text.split()
    if not words:
        return []

    segment_count = max(
        1,
        ceil(duration_ms / _MAX_SUBTITLE_SEGMENT_MS),
        ceil(len(words) / _MAX_SUBTITLE_WORDS),
    )
    segment_count = min(segment_count, len(words))
    words_per_segment = ceil(len(words) / segment_count)

    rows: list[tuple[int, int, str]] = []
    consumed = 0
    for index in range(0, len(words), words_per_segment):
        part_words = words[index : index + words_per_segment]
        next_consumed = min(len(words), consumed + len(part_words))
        row_start = start_ms + round(duration_ms * consumed / len(words))
        row_end = start_ms + round(duration_ms * next_consumed / len(words))
        if row_end <= row_start:
            row_end = min(end_ms, row_start + 1)
        rows.append((row_start, min(end_ms, row_end), " ".join(part_words)))
        consumed = next_consumed
    return rows


def _normalize_text(text: str, language: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\u200f", "").replace("\u200e", "")
    if (language or "fa").lower() == "fa":
        normalized = normalized.translate(_PERSIAN_REPLACEMENTS)
    return _CONTROL_WHITESPACE_RE.sub(" ", normalized).strip()


def _looks_like_repeated_noise(text: str) -> bool:
    words = _WORD_RE.findall(text.lower())
    if len(words) >= 8:
        counts = Counter(words)
        dominant_word, dominant_count = counts.most_common(1)[0]
        if len(dominant_word) >= 2 and dominant_count >= 8 and dominant_count / len(words) >= 0.7:
            return True

    letters = [char for char in text if char.isalpha()]
    if len(letters) < 16:
        return False
    counts = Counter(letters)
    dominant_count = counts.most_common(1)[0][1]
    unique_letters = len(counts)
    if unique_letters <= 3 and _max_letter_run(text) >= 12:
        return True
    return unique_letters <= 2 and dominant_count / len(letters) >= 0.75


def _looks_like_instruction_echo(text: str) -> bool:
    lowered = text.lower()
    marker_hits = sum(1 for marker in _INSTRUCTION_ECHO_MARKERS if marker in lowered)
    return marker_hits >= 1


def _max_letter_run(text: str) -> int:
    longest = 0
    current = 0
    previous = ""
    for char in text:
        if not char.isalpha():
            current = 0
            previous = ""
            continue
        if char == previous:
            current += 1
        else:
            current = 1
            previous = char
        longest = max(longest, current)
    return longest
