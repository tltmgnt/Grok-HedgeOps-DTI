"""Phase 47 authenticated fencing issuance audit checkpoint tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.fence_audit_checkpoint import (
    create_fence_audit_checkpoint, verify_fence_audit_checkpoint)

TOKEN = "phase47-test-operator-token-long"
KEY = b"f" * 32


class FenceAuditCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.sqlite3"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)

    def tearDown(self):
        self.temp.cleanup()

    def issue(self):
        return self.authority.acquire_authorized(
            "operator-1", TOKEN, configured_token=TOKEN)

    def checkpoint(self):
        return create_fence_audit_checkpoint(self.authority, KEY)

    def test_empty_audit_rejected(self):
        with self.assertRaises(ValueError):
            self.checkpoint()

    def test_checkpoint_verifies(self):
        self.issue()
        self.assertTrue(verify_fence_audit_checkpoint(
            self.authority, self.checkpoint(), KEY))

    def test_later_issuance_preserves_ancestor(self):
        self.issue()
        checkpoint = self.checkpoint()
        self.issue()
        self.assertTrue(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))

    def test_wrong_key_rejected(self):
        self.issue()
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, self.checkpoint(), b"g" * 32))

    def test_modified_checkpoint_rejected(self):
        self.issue()
        checkpoint = self.checkpoint()
        checkpoint["generation"] += 1
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))

    def test_invalid_key_rejected(self):
        self.issue()
        with self.assertRaises(ValueError):
            self.checkpoint_key_short()
    def checkpoint_key_short(self):
        return create_fence_audit_checkpoint(self.authority, b"short")

    def test_truncated_audit_rejected(self):
        self.issue()
        checkpoint = self.checkpoint()
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM recovery_fence_issuance")
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))

    def test_divergent_audit_rejected(self):
        self.issue()
        checkpoint = self.checkpoint()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE recovery_fence_issuance SET event_hash=?",
                       ("a" * 64,))
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))

    def test_rollback_generation_rejected(self):
        self.issue()
        checkpoint = self.checkpoint()
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM recovery_fence")
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))

    def test_noncanonical_checkpoint_rejected(self):
        self.issue()
        checkpoint = self.checkpoint()
        checkpoint["extra"] = "ignored?"
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))

    def test_suffix_tampering_rejected(self):
        self.issue()
        checkpoint = self.checkpoint()
        self.issue()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE recovery_fence_issuance SET previous_hash=? "
                       "WHERE generation=2", ("0" * 64,))
        self.assertFalse(verify_fence_audit_checkpoint(
            self.authority, checkpoint, KEY))


if __name__ == "__main__":
    unittest.main()
