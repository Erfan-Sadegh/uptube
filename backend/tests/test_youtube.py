import unittest

from app.services.youtube import _resumable_chunk_size


class YouTubeTests(unittest.TestCase):
    def test_resumable_chunk_size_has_google_minimum(self):
        self.assertEqual(_resumable_chunk_size(1), 256 * 1024)

    def test_resumable_chunk_size_rounds_down_to_256kb_multiple(self):
        self.assertEqual(_resumable_chunk_size(1024 * 1024 + 1), 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
