import unittest

from app.services.avalai import _parse_words


class AvalAITests(unittest.TestCase):
    def test_parse_words_ignores_invalid_items(self):
        words = _parse_words(
            [
                {"word": "سلام", "start": 0, "end": 0.4},
                {"word": "", "start": 0.4, "end": 0.6},
                {"word": "دنیا", "start": "0.6", "end": "1.2"},
                {"word": "bad", "start": None, "end": 2},
            ]
        )
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0].text, "سلام")
        self.assertEqual(words[0].start_ms, 0)
        self.assertEqual(words[0].end_ms, 400)
        self.assertEqual(words[1].text, "دنیا")
        self.assertEqual(words[1].start_ms, 600)
        self.assertEqual(words[1].end_ms, 1200)


if __name__ == "__main__":
    unittest.main()
