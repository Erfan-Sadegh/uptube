import unittest

from app.models import uuid
from app.services.aparat import AparatValidationError, extract_video_hash, validate_aparat_url


class AparatValidationTests(unittest.TestCase):
    def test_accepts_aparat_video_url(self):
        self.assertEqual(
            validate_aparat_url("https://www.aparat.com/v/example"),
            "https://www.aparat.com/v/example",
        )

    def test_rejects_non_aparat_url(self):
        with self.assertRaises(AparatValidationError):
            validate_aparat_url("https://youtube.com/watch?v=x")

    def test_rejects_root_url(self):
        with self.assertRaises(AparatValidationError):
            validate_aparat_url("https://www.aparat.com/")

    def test_extracts_video_hash(self):
        self.assertEqual(extract_video_hash("https://www.aparat.com/v/drmw198"), "drmw198")

    def test_generated_ids_are_short(self):
        self.assertLessEqual(len(uuid()), 12)


if __name__ == "__main__":
    unittest.main()
