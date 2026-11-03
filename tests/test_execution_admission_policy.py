"""Persistent execution admission policy regression tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.execution_admission_policy import (
    execution_custody_required, require_execution_custody)
from hedgeops.recovery_fence import RecoveryFenceAuthority


class AdmissionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.db"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_disabled_before_enabling(self):
        with self.authority._connect() as db:
            self.assertFalse(execution_custody_required(db))

    def test_persists_across_reopen(self):
        require_execution_custody(self.authority)
        reopened = RecoveryFenceAuthority(self.path)
        with reopened._connect() as db:
            self.assertTrue(execution_custody_required(db))

    def test_idempotent(self):
        require_execution_custody(self.authority)
        require_execution_custody(self.authority)
        with self.authority._connect() as db:
            self.assertTrue(execution_custody_required(db))


if __name__ == "__main__":
    unittest.main()
