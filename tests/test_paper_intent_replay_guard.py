"""Local submission attempt reservation tests; no broker network calls."""
import json
from pathlib import Path
import tempfile
import unittest

from paper_purchase_decision import reserve_local_submission


class LocalReplayGuardTests(unittest.TestCase):
    def test_reservation_survives_repeated_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            reserve_local_submission(path, 'hedgeops-12345678')
            marker = path / 'submission-attempt.json'
            self.assertEqual(json.loads(marker.read_text())['state'], 'ATTEMPT_RESERVED')
            original = marker.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'already reserved'):
                reserve_local_submission(path, 'hedgeops-12345678')
            self.assertEqual(marker.read_bytes(), original)

    def test_different_id_same_output_directory_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            reserve_local_submission(path, 'hedgeops-12345678')
            with self.assertRaises(RuntimeError):
                reserve_local_submission(path, 'hedgeops-87654321')


if __name__ == '__main__':
    unittest.main()
