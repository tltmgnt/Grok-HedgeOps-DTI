"""Phase 56 three-namespace custody gate regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.fence_audit_custody import publish_fence_audit_checkpoint
from hedgeops.custody_alert_journal import CustodyAlertJournal
from hedgeops.custody_alert_anchor import publish_alert_checkpoint
from hedgeops.recovery_execution_audit import ensure_execution_audit, append_execution_event
from hedgeops.recovery_execution_custody import publish_execution_checkpoint
from hedgeops.recovery_execution_custody_gate import verify_recovery_execution_custody_gate

KEY = b"k" * 32
TOKEN = "phase56-test-operator-token-long"


class MemoryCustodian:
    def __init__(self):
        self.record = None

    def read(self):
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        if self.record != expected:
            return False
        self.record = dict(new)
        return True


class TripleGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.authority = RecoveryFenceAuthority(root / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.fence_custody = MemoryCustodian()
        self.fence_checkpoint = publish_fence_audit_checkpoint(
            self.authority, KEY, self.fence_custody)
        self.journal = CustodyAlertJournal(root / "alerts.db")
        self.journal.append({"baseline": True, "counter_reset": False, "alerts": []})
        self.alert_custody = MemoryCustodian()
        self.alert_checkpoint = publish_alert_checkpoint(
            self.journal, KEY, self.alert_custody)
        ensure_execution_audit(self.authority)
        with sqlite3.connect(root / "fence.db") as db:
            db.execute("BEGIN IMMEDIATE")
            append_execution_event(db, self.generation)
            db.commit()
        self.execution_custody = MemoryCustodian()
        self.execution_checkpoint = publish_execution_checkpoint(
            self.authority, KEY, self.execution_custody)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, key=KEY):
        return verify_recovery_execution_custody_gate(
            self.authority, self.fence_checkpoint, KEY, self.fence_custody,
            self.journal, self.alert_checkpoint, KEY, self.alert_custody,
            self.generation, self.execution_checkpoint, key,
            self.execution_custody)

    def test_valid(self):
        self.assertTrue(self.check())

    def test_missing_execution_custody(self):
        self.execution_custody.record = None
        self.assertFalse(self.check())

    def test_wrong_execution_key(self):
        self.assertFalse(self.check(b"x" * 32))

    def test_substituted_execution_fingerprint(self):
        self.execution_custody.record["checkpoint_sha256"] = "0" * 64
        self.assertFalse(self.check())

    def test_stale_generation(self):
        self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.assertFalse(self.check())

    def test_missing_alert_custody(self):
        self.alert_custody.record = None
        self.assertFalse(self.check())

    def test_missing_fence_custody(self):
        self.fence_custody.record = None
        self.assertFalse(self.check())


if __name__ == "__main__":
    unittest.main()
