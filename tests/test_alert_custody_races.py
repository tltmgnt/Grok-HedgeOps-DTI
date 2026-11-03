"""Phase 42 race-aware alert custody regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.custody_alert_anchor import (
    AlertCustodyError, publish_alert_checkpoint, verify_custodied_alert_journal)
from hedgeops.custody_alert_journal import CustodyAlertJournal

KEY = b"k" * 32


def evaluation():
    return {"baseline": False, "counter_reset": False,
            "alerts": [{"event": "service_unavailable",
                        "count": 1, "threshold": 1}]}


class RaceCustodian:
    def __init__(self):
        self.value = None
        self.reads = 0
        self.advance_at = None
        self.conflict = False

    def read(self):
        self.reads += 1
        if self.reads == self.advance_at and self.value is not None:
            self.value = {"sequence": self.value["sequence"] + 1,
                          "checkpoint_sha256": "f" * 64}
        return None if self.value is None else dict(self.value)

    def compare_and_swap(self, expected, new):
        if self.conflict or self.value != expected:
            return False
        self.value = dict(new)
        return True


class RaceAwareAnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = CustodyAlertJournal(Path(self.temp.name) / "alerts.sqlite3")
        self.journal.append(evaluation())
        self.custodian = RaceCustodian()

    def tearDown(self):
        self.temp.cleanup()

    def test_publication_readback_matches(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.assertEqual(self.custodian.reads, 2)
        self.assertTrue(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_publication_detects_immediate_advance(self):
        self.custodian.advance_at = 2
        with self.assertRaisesRegex(AlertCustodyError, "changed after publication"):
            publish_alert_checkpoint(self.journal, KEY, self.custodian)

    def test_publication_conflict_rejected(self):
        self.custodian.conflict = True
        with self.assertRaisesRegex(AlertCustodyError, "CAS conflict"):
            publish_alert_checkpoint(self.journal, KEY, self.custodian)

    def test_verification_rechecks_after_journal(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.custodian.reads = 0
        self.custodian.advance_at = 2
        self.assertFalse(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))
        self.assertEqual(self.custodian.reads, 2)

    def test_verification_detects_mutation_during_check(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        original = self.custodian.read
        calls = [0]

        def read():
            calls[0] += 1
            if calls[0] == 2:
                self.custodian.value["sequence"] += 1
            return original()

        with patch.object(self.custodian, "read", side_effect=read):
            self.assertFalse(verify_custodied_alert_journal(
                self.journal, checkpoint, KEY, self.custodian))

    def test_verification_rejects_disappearing_custody(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        original = self.custodian.read
        calls = [0]

        def read():
            calls[0] += 1
            return original() if calls[0] == 1 else None

        with patch.object(self.custodian, "read", side_effect=read):
            self.assertFalse(verify_custodied_alert_journal(
                self.journal, checkpoint, KEY, self.custodian))

    def test_invalid_journal_does_not_succeed(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        self.journal.append(evaluation())
        self.assertTrue(verify_custodied_alert_journal(
            self.journal, checkpoint, KEY, self.custodian))

    def test_invalid_second_custody_read_fails_closed(self):
        checkpoint = publish_alert_checkpoint(self.journal, KEY, self.custodian)
        original = self.custodian.read
        calls = [0]

        def read():
            calls[0] += 1
            return original() if calls[0] == 1 else {"sequence": True}

        with patch.object(self.custodian, "read", side_effect=read):
            self.assertFalse(verify_custodied_alert_journal(
                self.journal, checkpoint, KEY, self.custodian))


if __name__ == "__main__":
    unittest.main()
