"""Phase 49 recovery gate regression tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.fence_audit_custody import publish_fence_audit_checkpoint
from hedgeops.custody_alert_journal import CustodyAlertJournal
from hedgeops.custody_alert_anchor import publish_alert_checkpoint
from hedgeops.recovery_custody_gate import verify_recovery_custody_gate

KEY = b"k" * 32
TOKEN = "phase49-operator-token-long-enough"


class FakeCustodian:
    def __init__(self):
        self.record = None
        self.read_count = 0
        self.mutate_at = None

    def read(self):
        self.read_count += 1
        if self.read_count == self.mutate_at and self.record:
            self.record = dict(self.record)
            self.record["generation" if "generation" in self.record else "sequence"] += 1
        return None if self.record is None else dict(self.record)

    def compare_and_swap(self, expected, new):
        if self.record != expected:
            return False
        self.record = dict(new)
        return True


class RecoveryCustodyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.authority = RecoveryFenceAuthority(root / "fence.db", strict=True)
        self.generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.fence_custody = FakeCustodian()
        self.fence_checkpoint = publish_fence_audit_checkpoint(
            self.authority, KEY, self.fence_custody)
        self.journal = CustodyAlertJournal(root / "alerts.db")
        self.journal.append({"baseline": True, "counter_reset": False, "alerts": []})
        self.alert_custody = FakeCustodian()
        self.alert_checkpoint = publish_alert_checkpoint(
            self.journal, KEY, self.alert_custody)

    def tearDown(self):
        self.temp.cleanup()

    def check(self, generation=None, fence_key=KEY, alert_key=KEY):
        return verify_recovery_custody_gate(
            self.authority, self.fence_checkpoint, fence_key,
            self.fence_custody, self.journal, self.alert_checkpoint,
            alert_key, self.alert_custody,
            self.generation if generation is None else generation)

    def test_valid_cross_namespace_gate(self):
        self.assertTrue(self.check())

    def test_wrong_generation(self):
        self.assertFalse(self.check(generation=999))

    def test_wrong_fence_key(self):
        self.assertFalse(self.check(fence_key=b"x" * 32))

    def test_wrong_alert_key(self):
        self.assertFalse(self.check(alert_key=b"x" * 32))

    def test_missing_fence_custody(self):
        self.fence_custody.record = None
        self.assertFalse(self.check())

    def test_missing_alert_custody(self):
        self.alert_custody.record = None
        self.assertFalse(self.check())

    def test_fence_substitution(self):
        self.fence_custody.record["audit_sha256"] = "0" * 64
        self.assertFalse(self.check())

    def test_alert_substitution(self):
        self.alert_custody.record["checkpoint_sha256"] = "0" * 64
        self.assertFalse(self.check())

    def test_fence_changes_during_check(self):
        self.fence_custody.read_count = 0
        self.fence_custody.mutate_at = 2
        self.assertFalse(self.check())

    def test_alert_changes_during_check(self):
        self.alert_custody.read_count = 0
        self.alert_custody.mutate_at = 2
        self.assertFalse(self.check())

    def test_new_generation_invalidates_old_gate(self):
        self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        self.assertFalse(self.check())


if __name__ == "__main__":
    unittest.main()
