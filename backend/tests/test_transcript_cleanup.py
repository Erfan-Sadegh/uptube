import unittest
from dataclasses import dataclass

from app.services.transcript_cleanup import clean_transcript_text, split_text_for_subtitle_rows
from app.services.transcript_cleanup import subtitle_rows_from_timed_words_and_text
from app.services.transcript_cleanup import subtitle_rows_from_timed_words


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    text: str


class TranscriptCleanupTests(unittest.TestCase):
    def test_normalizes_persian_arabic_letters_and_spacing(self):
        text = "\u0633\u0644\u0627\u0645   \u064a\u0648\u062a\u064a\u0648\u0628  \u0643\u0627\u0631\u0645\u0646\u062f"
        self.assertEqual(clean_transcript_text(text, "fa"), "\u0633\u0644\u0627\u0645 \u06cc\u0648\u062a\u06cc\u0648\u0628 \u06a9\u0627\u0631\u0645\u0646\u062f")

    def test_drops_repeated_single_word_noise(self):
        text = " ".join(["\u0627\u06cc\u0631\u0627\u0646"] * 12)
        self.assertEqual(clean_transcript_text(text, "fa"), "")

    def test_drops_repeated_letter_noise(self):
        self.assertEqual(clean_transcript_text("\u0627" * 40 + "\u0648" * 20, "fa"), "")

    def test_preserves_normal_creator_sentence(self):
        text = "\u0627\u0645\u0631\u0648\u0632 \u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645 \u062a\u0646\u0638\u06cc\u0645\u0627\u062a OBS \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u0633\u062a\u0631\u06cc\u0645 \u0628\u0631\u0631\u0633\u06cc \u06a9\u0646\u0645."
        self.assertEqual(clean_transcript_text(text, "fa"), text)

    def test_drops_echoed_internal_instruction_text(self):
        text = "\u0645\u0648\u0633\u06cc\u0642\u06cc\u060c \u0633\u06a9\u0648\u062a \u0648 \u0622\u0648\u0627\u0647\u0627\u06cc \u0646\u0627\u0645\u0641\u0647\u0648\u0645 \u0631\u0627 \u0646\u0646\u0648\u06cc\u0633."
        self.assertEqual(clean_transcript_text(text, "fa"), "")

    def test_splits_long_chunk_text_into_shorter_caption_rows(self):
        text = " ".join(f"word{i}" for i in range(1, 31))
        rows = split_text_for_subtitle_rows(text, 0, 60_000)
        self.assertGreater(len(rows), 1)
        self.assertLessEqual(max(end - start for start, end, _ in rows), 14_000)
        self.assertEqual(rows[0][0], 0)
        self.assertEqual(rows[-1][1], 60_000)

    def test_groups_timed_words_into_readable_subtitle_rows(self):
        words = [Word(index * 700, index * 700 + 500, f"word{index}") for index in range(20)]
        rows = subtitle_rows_from_timed_words(words, "en")
        self.assertGreater(len(rows), 1)
        self.assertLessEqual(max(len(text.split()) for _, _, text in rows), 11)
        self.assertEqual(rows[0][0], 0)
        self.assertEqual(rows[-1][1], words[-1].end_ms)

    def test_aligns_clean_text_to_timed_rows_when_word_counts_are_close(self):
        source_words = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu".split()
        words = [Word(index * 700, index * 700 + 500, word) for index, word in enumerate(source_words)]
        clean_text = "today we review capture settings for streaming and recording with better audio levels"
        result = subtitle_rows_from_timed_words_and_text(words, clean_text, 10_000, "en")
        self.assertEqual(result.strategy, "timed_alignment")
        self.assertEqual(result.clean_word_count, 13)
        self.assertEqual(result.timing_word_count, 12)
        self.assertEqual(result.rows[0][0], 0)
        self.assertEqual(result.rows[-1][1], words[-1].end_ms)
        self.assertIn("today", result.rows[0][2])

    def test_uses_duration_distribution_when_timing_text_missed_many_words(self):
        words = [Word(0, 500, "short"), Word(10_000, 10_500, "miss")]
        clean_text = (
            "many creators explain their setup workflow camera lighting microphone editing upload "
            "schedule audience retention chapters title thumbnail analytics comments community and growth"
        )
        result = subtitle_rows_from_timed_words_and_text(words, clean_text, 30_000, "en")
        self.assertEqual(result.strategy, "duration_distribution")
        self.assertEqual(result.rows[0][0], 0)
        self.assertEqual(result.rows[-1][1], 30_000)
        self.assertGreater(len(result.rows), 2)


if __name__ == "__main__":
    unittest.main()
