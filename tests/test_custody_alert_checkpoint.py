"""Phase 39 authenticated alert checkpoint and rollback regressions."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.custody_alert_checkpoint import (
    create_alert_checkpoint, verify_alert_checkpoint)
from hedgeops.custody_alert_journal import CustodyAlertJournal

KEY = b"k" * 32
OTHER_KEY = b"z" * 32


def alert():
    return {"baseline": False, "counter_reset": False,
            "alerts": [{"event": "service_unavailable",
                        "count": 1, "threshold": 1}]}


class AlertCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "alerts.sqlite3"
        self.journal = CustodyAlertJournal(self.path)
        self.journal.append(alert())

    def tearDown(self):
        self.temp.cleanup()

    def test_matching_checkpoint(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        self.assertTrue(verify_alert_checkpoint(self.journal, checkpoint, KEY))

    def test_later_events_preserve_checkpoint_ancestry(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        self.journal.append(alert())
        self.assertTrue(verify_alert_checkpoint(self.journal, checkpoint, KEY))

    def test_deleted_suffix_detected(self):
        self.journal.append(alert())
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM custody_alert_events WHERE sequence=2")
        self.assertFalse(verify_alert_checkpoint(self.journal, checkpoint, KEY))

    def test_replaced_valid_journal_detected(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM custody_alert_events")
        self.journal.append({"baseline": True, "counter_reset": False, "alerts": []})
        self.assertTrue(self.journal.verify())
        self.assertFalse(verify_alert_checkpoint(self.journal, checkpoint, KEY))

    def test_wrong_key_rejected(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        self.assertFalse(verify_alert_checkpoint(self.journal, checkpoint, OTHER_KEY))

    def test_tampered_checkpoint_rejected(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        checkpoint["event_hash"] = "0" * 64
        self.assertFalse(verify_alert_checkpoint(self.journal, checkpoint, KEY))

    def test_malformed_checkpoint_rejected(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        for mutation in ({"sequence": True}, {"sequence": 0},
                         {"extra": "unexpected"}, {"authentication_tag": "bad"}):
            changed = dict(checkpoint, **mutation)
            self.assertFalse(verify_alert_checkpoint(self.journal, changed, KEY))

    def test_short_key_rejected(self):
        with self.assertRaises(ValueError):
            create_alert_checkpoint(self.journal, b"short")
        with self.assertRaises(ValueError):
            verify_alert_checkpoint(self.journal, {}, b"short")

    def test_empty_journal_cannot_be_checkpointed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM custody_alert_events")
        with self.assertRaises(ValueError):
            create_alert_checkpoint(self.journal, KEY)

    def test_corrupted_journal_cannot_be_checkpointed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE custody_alert_events SET event_hash='bad'")
        with self.assertRaises(ValueError):
            create_alert_checkpoint(self.journal, KEY)

    def test_checkpoint_does_not_expose_key_or_payload(self):
        checkpoint = create_alert_checkpoint(self.journal, KEY)
        self.assertEqual(set(checkpoint),
                         {"scheme", "sequence", "event_hash", "authentication_tag"})
        self.assertNotIn("service_unavailable", str(checkpoint))


if __name__ == "__main__":
    unittest.main()
