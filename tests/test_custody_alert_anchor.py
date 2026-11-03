"""Phase 40 independent alert-checkpoint custody regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.custody_alert_anchor import (
    AlertCustodyError, publish_alert_checkpoint, verify_custodied_alert_journal)
from hedgeops.custody_alert_journal import CustodyAlertJournal

KEY = b"j" * 32


class FakeCustodian:
    """In-memory test double; NOT independently durable or trusted."""
    def __init__(self):
        self.value = None
        self.conflict = False

    def read(self):
        return None if self.value is None else dict(self.value)

    def compare_and_swap(self, expected, new):
        if self.conflict or self.value != expected:
            return False
        self.value = dict(new)
        return True


def evaluation():
    return {"baseline": False, "counter_reset": False,
            "alerts": [{"event": "service_unavailable",
                        "count": 1, "threshold": 1}]}


class AlertAnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "alerts.sqlite3"
        self.journal = CustodyAlertJournal(self.path)
        self.journal.append(evaluation())
        self.custodian = FakeCustodian()

    def tearDown(self):
        self.temp.cleanup()

    def test_publish_and_verify(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.assertTrue(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_missing_custody_fails_closed(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.custodian.value = None
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_duplicate_publication_rejected(self):
        publish_alert_checkpoint(self.journal, KEY, self.custodian)
        with self.assertRaises(AlertCustodyError):
            publish_alert_checkpoint(self.journal, KEY, self.custodian)

    def test_conflicting_publication_rejected(self):
        self.custodian.conflict = True
        with self.assertRaises(AlertCustodyError):
            publish_alert_checkpoint(self.journal, KEY, self.custodian)

    def test_newer_custody_rejects_old_checkpoint(self):
        old = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.journal.append(evaluation())
        newer = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, old, KEY, self.custodian))
        self.assertTrue(verify_custodied_alert_journal(
            self.journal, newer, KEY, self.custodian))

    def test_valid_later_suffix_accepted(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.journal.append(evaluation())
        self.assertTrue(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_truncated_journal_rejected(self):
        self.journal.append(evaluation())
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM custody_alert_events WHERE sequence=2")
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_wrong_key_rejected(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, checkpoint, b"z" * 32, self.custodian))

    def test_malformed_custody_rejected(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.custodian.value["sequence"] = True
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_fingerprint_substitution_rejected(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.custodian.value["checkpoint_sha256"] = "0" * 64
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_invalid_journal_cannot_publish(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE custody_alert_events SET event_hash='bad'")
        with self.assertRaises(ValueError):
            publish_alert_checkpoint(self.journal, KEY, self.custodian)


if __name__ == "__main__":
    unittest.main()
