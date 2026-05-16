import unittest

from app.services.metis import (
    extract_srt_from_metis_response,
    extract_text_from_metis_response,
    map_metis_status,
)


class MetisTests(unittest.TestCase):
    def test_status_mapping(self):
        self.assertEqual(map_metis_status("QUEUE"), "transcribing")
        self.assertEqual(map_metis_status("WAITING"), "transcribing")
        self.assertEqual(map_metis_status("RUNNING"), "transcribing")
        self.assertEqual(map_metis_status("COMPLETED"), "completed")
        self.assertEqual(map_metis_status("ERROR"), "failed")
        self.assertEqual(map_metis_status("CANCELLED"), "failed")

    def test_extracts_content_srt(self):
        srt = "1\n00:00:00,000 --> 00:00:01,000\nسلام\n"
        data = {"generations": [{"content": srt}]}
        self.assertEqual(extract_srt_from_metis_response(data), srt)

    def test_extracts_raw_response_srt(self):
        srt = "1\n00:00:00,000 --> 00:00:01,000\nسلام\n"
        data = {"rawResponse": {"srt": srt}}
        self.assertEqual(extract_srt_from_metis_response(data), srt)

    def test_extracts_nested_text_response(self):
        data = {"rawResponse": '{"text":"Hello","duration":4.0}'}
        result = extract_text_from_metis_response(data)
        self.assertEqual(result.text, "Hello")
        self.assertEqual(result.duration_seconds, 4.0)


if __name__ == "__main__":
    unittest.main()
