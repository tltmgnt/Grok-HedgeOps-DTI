"""Phase 54 execution custody namespace regressions."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase, _etag
from hedgeops.https_custody import HTTPSExecutionCheckpointCustodian

TOKEN = "execution-custody-token-very-long"


class ExecutionNamespaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = CustodyDatabase(Path(self.tmp.name) / "custody.db")

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, sequence, digest="a"):
        return {"sequence": sequence, "checkpoint_sha256": digest * 64}

    def test_initial_publication(self):
        first = self.record(1)
        self.assertTrue(self.database.cas_execution("*", first))
        self.assertEqual(self.database.read_execution(), first)

    def test_reject_initial_sequence_above_one(self):
        self.assertFalse(self.database.cas_execution("*", self.record(2)))

    def test_monotonic_update(self):
        first = self.record(1)
        self.assertTrue(self.database.cas_execution("*", first))
        second = self.record(2, "b")
        self.assertTrue(self.database.cas_execution(_etag(first), second))
        self.assertEqual(self.database.read_execution(), second)

    def test_stale_etag(self):
        first = self.record(1)
        self.database.cas_execution("*", first)
        self.assertFalse(self.database.cas_execution('"stale"', self.record(2)))

    def test_replay_rejected(self):
        first = self.record(1)
        self.database.cas_execution("*", first)
        self.assertFalse(self.database.cas_execution(_etag(first), first))

    def test_namespaces_are_isolated(self):
        self.database.cas_execution("*", self.record(1))
        self.assertIsNone(self.database.read())
        self.assertIsNone(self.database.read_alert())
        self.assertIsNone(self.database.read_fence_audit())

    def test_invalid_digest_rejected(self):
        with self.assertRaises(ValueError):
            self.database.cas_execution("*", {
                "sequence": 1, "checkpoint_sha256": "invalid"})

    def test_https_adapter_path_restriction(self):
        with self.assertRaises(ValueError):
            HTTPSExecutionCheckpointCustodian(
                "https://example.com/v1/receipt", TOKEN)

    def test_https_adapter_record_validation(self):
        client = HTTPSExecutionCheckpointCustodian(
            "https://example.com/v1/execution-checkpoint", TOKEN)
        self.assertEqual(client._validate_record(self.record(1)), self.record(1))
        with self.assertRaises(ValueError):
            client._validate_record({"sequence": True,
                                     "checkpoint_sha256": "a" * 64})


if __name__ == "__main__":
    unittest.main()
