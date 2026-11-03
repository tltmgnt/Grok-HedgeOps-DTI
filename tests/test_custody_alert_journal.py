"""Phase 38 durable alert journal regression tests."""
import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.custody_alert_journal import CustodyAlertJournal
from hedgeops.custody_alerts import CustodyAlertMonitor
from hedgeops.custody_metrics import CustodyMetrics


def evaluation(event="service_unavailable"):
    return {"baseline": False, "counter_reset": False,
            "alerts": [{"event": event, "count": 2, "threshold": 1}]}


class FakeServer:
    rejected_connections = 0


class AlertJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "alerts.sqlite3"
        self.journal = CustodyAlertJournal(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_append_and_verify(self):
        record = self.journal.append(evaluation())
        self.assertEqual(record["sequence"], 1)
        self.assertTrue(self.journal.verify())
        self.assertEqual(self.journal.head(), record)

    def test_reopen_persists(self):
        self.journal.append(evaluation())
        self.assertTrue(CustodyAlertJournal(self.path).verify())
        self.assertEqual(CustodyAlertJournal(self.path).head()["sequence"], 1)

    def test_empty_journal(self):
        self.assertTrue(self.journal.verify())
        self.assertEqual(self.journal.head(),
                         {"sequence": 0, "event_hash": "GENESIS"})

    def test_tampered_payload_rejected(self):
        self.journal.append(evaluation())
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE custody_alert_events SET payload='{}' WHERE sequence=1")
        self.assertFalse(self.journal.verify())
        with self.assertRaises(ValueError):
            self.journal.append(evaluation())

    def test_tampered_hash_rejected(self):
        self.journal.append(evaluation())
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE custody_alert_events SET event_hash='bad' WHERE sequence=1")
        self.assertFalse(self.journal.verify())

    def test_deleted_middle_record_rejected(self):
        for _ in range(3):
            self.journal.append(evaluation())
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM custody_alert_events WHERE sequence=2")
        self.assertFalse(self.journal.verify())

    def test_concurrent_writes_serialized(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(lambda _: self.journal.append(evaluation()),
                                    range(8)))
        self.assertEqual(sorted(row["sequence"] for row in records),
                         list(range(1, 9)))
        self.assertTrue(self.journal.verify())

    def test_invalid_alert_rejected(self):
        bad = evaluation()
        bad["alerts"][0]["event"] = "secret arbitrary event"
        with self.assertRaises(ValueError):
            self.journal.append(bad)

    def test_baseline_recorded(self):
        result = {"baseline": True, "counter_reset": False, "alerts": []}
        self.journal.append(result)
        self.assertTrue(self.journal.verify())

    def test_real_monitor_evaluation_recorded(self):
        metrics = CustodyMetrics()
        monitor = CustodyAlertMonitor()
        server = FakeServer()
        self.journal.append(monitor.sample(metrics, server))
        metrics.record("PUT", "receipt", 503)
        self.journal.append(monitor.sample(metrics, server))
        self.assertEqual(self.journal.head()["sequence"], 2)
        self.assertTrue(self.journal.verify())


if __name__ == "__main__":
    unittest.main()
