import unittest

from app.services.transcript_cleanup import build_transcription_prompt, clean_transcript_text


class TranscriptCleanupTests(unittest.TestCase):
    def test_persian_prompt_uses_title_and_no_translation_instruction(self):
        prompt = build_transcription_prompt("fa", "\u0622\u0645\u0648\u0632\u0634 OBS \u0628\u0631\u0627\u06cc \u06af\u06cc\u0645\u0631\u0647\u0627")
        self.assertIn("\u062a\u0631\u062c\u0645\u0647 \u0646\u06a9\u0646", prompt)
        self.assertIn("OBS", prompt)

    def test_english_prompt_uses_title_and_no_translation_instruction(self):
        prompt = build_transcription_prompt("en", "Minecraft speedrun tips")
        self.assertIn("Do not translate", prompt)
        self.assertIn("Minecraft speedrun tips", prompt)

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


if __name__ == "__main__":
    unittest.main()
