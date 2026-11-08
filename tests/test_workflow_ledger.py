import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from workflow_ledger import Ledger, start_of


class LedgerTests(unittest.TestCase):
    def test_reopen_duplicate_and_conflict(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'ledger.sqlite3'
            item = {'observed_at_utc': '2026-11-09T16:00:00Z', 'status': 'OK', 'strategy_version': 'v1'}
            ledger = Ledger(path)
            ledger.ingest('a', item)
            ledger.close()
            ledger = Ledger(path)
            try:
                ledger.ingest('a', item)
                with self.assertRaises(ValueError):
                    ledger.ingest('a', {**item, 'status': 'ERROR'})
                report = ledger.report('daily', datetime(2026, 11, 9, 17, tzinfo=timezone.utc))
                self.assertEqual(report['sessions'], 1)
                self.assertEqual(report['status_counts']['OK'], 1)
                self.assertEqual(report['latest_observation_age_seconds'], 3600)
            finally:
                ledger.close()

    def test_boundaries_and_future_exclusion(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root) / 'ledger.sqlite3')
            try:
                for identity, stamp in [('old', '2026-11-09T15:49:59Z'), ('edge', '2026-11-09T15:50:00Z'), ('future', '2026-11-09T16:00:01Z')]:
                    ledger.ingest(identity, {'observed_at_utc': stamp, 'status': 'OK', 'strategy_version': 'v1'})
                now = datetime(2026, 11, 9, 16, tzinfo=timezone.utc)
                self.assertEqual(ledger.report('10m', now)['sessions'], 1)
                self.assertEqual(start_of('quarterly', now).isoformat(), '2026-10-01T00:00:00+00:00')
                self.assertEqual(start_of('monthly', now).day, 1)
            finally:
                ledger.close()

    def test_empty_and_naive_time(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = Ledger(Path(root) / 'ledger.sqlite3')
            try:
                now = datetime.now(timezone.utc)
                self.assertEqual(ledger.report('1s', now)['coverage'], 'NO_OBSERVATIONS')
                with self.assertRaises(ValueError):
                    ledger.report('daily', datetime(2026, 1, 1))
            finally:
                ledger.close()
