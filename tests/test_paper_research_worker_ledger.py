import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import paper_research_worker as worker
from workflow_ledger import Ledger


class WorkerLedgerTests(unittest.TestCase):
    def test_failed_session_is_durable_and_not_retried(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / 'ledger.sqlite3'
            def session(command):
                output = Path(command[command.index('--output-dir') + 1])
                output.mkdir(parents=True)
                (output / 'session.json').write_text(json.dumps({
                    'observed_at_utc': '2026-11-09T16:00:00Z',
                    'strategy_version': 'test', 'status': 'ERROR'}))
                return 1
            with patch.object(worker, 'session_main', side_effect=session) as run, patch.object(worker.time, 'sleep') as sleep:
                self.assertEqual(worker.main(['--output-dir', str(Path(root) / 'runs'), '--ledger', str(db), '--monitor-only']), 1)
                run.assert_called_once()
                sleep.assert_not_called()
                self.assertIn('--monitor-only', run.call_args.args[0])
            ledger = Ledger(db)
            try:
                report = ledger.report('daily', datetime(2026, 11, 9, 17, tzinfo=timezone.utc))
                self.assertEqual(report['status_counts']['ERROR'], 1)
            finally:
                ledger.close()
