import re
import unicodedata
from collections import Counter


_CONTROL_WHITESPACE_RE = re.compile(r"\s+")
_REPEATED_LETTER_RE = re.compile(r"([^\W\d_])\1{4,}", re.UNICODE)
_REPEATED_PUNCTUATION_RE = re.compile(r"([!?.؟،,؛:])\1{2,}")
_REPEATED_WORD_RE = re.compile(r"\b([^\W\d_]{2,})(?:\s+\1){3,}\b", re.IGNORECASE | re.UNICODE)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

_PERSIAN_REPLACEMENTS = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
    }
)


def build_transcription_prompt(language: str, title: str | None = None) -> str:
    normalized_language = (language or "fa").lower()
    safe_title = _safe_context_title(title)
    if normalized_language == "en":
        prompt = (
            "Transcribe only clear spoken English for subtitles. Do not translate. "
            "Do not invent missing words. Ignore background music, silence, and unclear filler sounds. "
            "Keep creator names, game names, product names, and technical terms as heard."
        )
        if safe_title:
            prompt += f" Video context: {safe_title}."
        return prompt

    prompt = (
        "این فایل برای زیرنویس گفتار فارسی است. فقط گفتار واضح را به فارسی بنویس. "
        "ترجمه نکن و کلمات نامطمئن را حدس نزن. موسیقی، سکوت و آواهای نامفهوم را ننویس. "
        "نام افراد، بازی‌ها، برندها و اصطلاحات تخصصی را تا حد ممکن همان‌طور که شنیده می‌شود نگه دار."
    )
    if safe_title:
        prompt += f" زمینه ویدئو: {safe_title}."
    return prompt


def clean_transcript_text(text: str, language: str = "fa") -> str:
    normalized = _normalize_text(text, language)
    if not normalized:
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


def _normalize_text(text: str, language: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("\u200f", "").replace("\u200e", "")
    if (language or "fa").lower() == "fa":
        normalized = normalized.translate(_PERSIAN_REPLACEMENTS)
    return _CONTROL_WHITESPACE_RE.sub(" ", normalized).strip()


def _safe_context_title(title: str | None) -> str:
    if not title:
        return ""
    normalized = unicodedata.normalize("NFKC", title)
    normalized = _CONTROL_WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized[:120]


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
