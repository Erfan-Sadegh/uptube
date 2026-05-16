import unittest

from app.services.srt import format_timestamp, parse_srt, parse_timestamp, render_srt


class SrtTests(unittest.TestCase):
    def test_parse_and_render_srt(self):
        content = """1
00:00:01,000 --> 00:00:03,500
سلام دنیا

2
00:00:04,000 --> 00:00:05,000
خط دوم
"""
        segments = parse_srt(content)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].start_ms, 1000)
        self.assertEqual(segments[0].end_ms, 3500)
        self.assertEqual(segments[0].text, "سلام دنیا")
        rendered = render_srt([(item.index, item.start_ms, item.end_ms, item.text) for item in segments])
        self.assertIn("00:00:01,000 --> 00:00:03,500", rendered)

    def test_timestamp_roundtrip(self):
        self.assertEqual(parse_timestamp(format_timestamp(3_723_456)), 3_723_456)


if __name__ == "__main__":
    unittest.main()
