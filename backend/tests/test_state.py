import unittest

from app.jobs.state import JobStatus, can_transition


class StateTests(unittest.TestCase):
    def test_valid_pipeline_transition(self):
        self.assertTrue(can_transition(JobStatus.QUEUED, JobStatus.VALIDATING))

    def test_invalid_backwards_transition(self):
        self.assertFalse(can_transition(JobStatus.COMPLETED, JobStatus.TRANSCRIBING))


if __name__ == "__main__":
    unittest.main()
