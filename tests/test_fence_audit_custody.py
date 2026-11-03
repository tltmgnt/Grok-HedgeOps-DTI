"""Phase 48 fencing audit custody tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.fence_audit_custody import (
    FenceAuditCustodyError, audit_fingerprint, publish_fence_audit_checkpoint,
    verify_custodied_fence_audit, _record)

KEY = b"a" * 32
TOKEN = "phase48-test-operator-token-long"


class FakeCustodian:
    def __init__(self):
        self.value = None
        self.conflict = False
        self.advance_after_put = False
        self.reads = 0
        self.advance_at = None

    def read(self):
        self.reads += 1
        if self.reads == self.advance_at and self.value is not None:
            self.value = {"generation": self.value["generation"] + 1,
                          "audit_sha256": "f" * 64}
        return None if self.value is None else dict(self.value)

    def compare_and_swap(self, expected, new):
        if self.conflict or self.value != expected:
            return False
        self.value = dict(new)
        return True


class FenceAuditCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.sqlite3", strict=True)
        self.custodian = FakeCustodian()
        self.issue()

    def tearDown(self):
        self.temp.cleanup()

    def issue(self):
        return self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)

    def publish(self):
        return publish_fence_audit_checkpoint(
            self.authority, KEY, self.custodian)

    def verify(self, checkpoint):
        return verify_custodied_fence_audit(
            self.authority, checkpoint, KEY, self.custodian)

    def test_publish_and_verify(self):
        checkpoint = self.publish()
        self.assertTrue(self.verify(checkpoint))

    def test_fingerprint_is_hex(self):
        checkpoint = self.publish()
        self.assertEqual(len(audit_fingerprint(checkpoint)), 64)

    def test_second_publish_requires_advance(self):
        self.publish()
        with self.assertRaises(FenceAuditCustodyError):
            self.publish()

    def test_later_issuance_can_publish(self):
        self.publish()
        self.issue()
        checkpoint = self.publish()
        self.assertEqual(checkpoint["generation"], 2)
        self.assertTrue(self.verify(checkpoint))

    def test_old_checkpoint_rejected_after_advance(self):
        old = self.publish()
        self.issue()
        self.publish()
        self.assertFalse(self.verify(old))

    def test_conflicting_cas_rejected(self):
        self.custodian.conflict = True
        with self.assertRaisesRegex(FenceAuditCustodyError, "CAS conflict"):
            self.publish()

    def test_publication_race_rejected(self):
        self.custodian.advance_at = 2
        with self.assertRaisesRegex(FenceAuditCustodyError, "changed"):
            self.publish()

    def test_verification_race_rejected(self):
        checkpoint = self.publish()
        self.custodian.reads = 0
        self.custodian.advance_at = 2
        self.assertFalse(self.verify(checkpoint))

    def test_wrong_key_rejected(self):
        checkpoint = self.publish()
        self.assertFalse(verify_custodied_fence_audit(
            self.authority, checkpoint, b"b" * 32, self.custodian))

    def test_missing_custody_rejected(self):
        checkpoint = self.publish()
        self.custodian.value = None
        self.assertFalse(self.verify(checkpoint))

    def test_invalid_record_rejected(self):
        for invalid in ({"generation": True, "audit_sha256": "a" * 64},
                        {"generation": 1, "audit_sha256": "X" * 64},
                        {"generation": 1, "audit_sha256": "a" * 64,
                         "receipt_sha256": "b" * 64}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(FenceAuditCustodyError):
                    _record(invalid)

    def test_divergent_custody_rejected(self):
        checkpoint = self.publish()
        self.custodian.value["audit_sha256"] = "0" * 64
        self.assertFalse(self.verify(checkpoint))


if __name__ == "__main__":
    unittest.main()
