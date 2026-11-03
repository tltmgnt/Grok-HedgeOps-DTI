"""Phase 48 independent fence-audit SQLite CAS tests."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase
from hedgeops.store import canonical


class FenceAuditDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = CustodyDatabase(Path(self.temp.name) / "custody.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_initial_generation_can_exceed_one(self):
        record = {"generation": 7, "audit_sha256": "a" * 64}
        self.assertTrue(self.db.cas_fence_audit("*", record))
        self.assertEqual(self.db.read_fence_audit(), record)

    def test_cas_and_monotonicity(self):
        first = {"generation": 3, "audit_sha256": "a" * 64}
        self.assertTrue(self.db.cas_fence_audit("*", first))
        etag = '"' + hashlib.sha256(canonical(first).encode()).hexdigest() + '"'
        self.assertFalse(self.db.cas_fence_audit(etag, first))
        self.assertFalse(self.db.cas_fence_audit('"bad"', dict(first, generation=4)))
        self.assertTrue(self.db.cas_fence_audit(
            etag, {"generation": 4, "audit_sha256": "b" * 64}))

    def test_namespace_isolation(self):
        self.assertTrue(self.db.cas_fence_audit(
            "*", {"generation": 1, "audit_sha256": "a" * 64}))
        self.assertIsNone(self.db.read_alert())
        self.assertIsNone(self.db.read())


if __name__ == "__main__":
    unittest.main()
