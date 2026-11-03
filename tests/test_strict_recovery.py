"""End-to-end strict receipt-gated backup recovery tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.audit import export_checkpoint
from hedgeops.backup import backup_with_checkpoint
from hedgeops.floor_registry import publish_recovery_floor
from hedgeops.identity import ReviewerRegistry
from hedgeops.registry_receipt import export_registry_receipt, save_registry_receipt
from hedgeops.store import EventStore
from hedgeops.strict_recovery import verify_receipt_gated_recovery
from hedgeops.workflow import create_case

CHECKPOINT_KEY = b"c" * 32
FLOOR_KEY = b"f" * 32
RECEIPT_KEY = b"r" * 32
REVIEWERS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class StrictRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = EventStore(root / "live.sqlite3")
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.backup = root / "backup.sqlite3"
        self.checkpoint = root / "checkpoint.json"
        self.floors = root / "floors"
        self.floors.mkdir()
        self.receipt = root / "trusted-receipt.json"
        backup_with_checkpoint(
            self.store, self.case, REVIEWERS, self.backup, self.checkpoint,
            authentication_key=CHECKPOINT_KEY)
        publish_recovery_floor(
            self.store, export_checkpoint(self.store, self.case, REVIEWERS),
            self.floors, FLOOR_KEY)
        save_registry_receipt(
            export_registry_receipt(self.floors, FLOOR_KEY, RECEIPT_KEY),
            self.receipt)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _verify(self, **changes):
        options = dict(
            backup_path=self.backup, checkpoint_path=self.checkpoint,
            reviewer_registry=REVIEWERS, floor_directory=self.floors,
            trusted_receipt_path=self.receipt, checkpoint_key=CHECKPOINT_KEY,
            floor_key=FLOOR_KEY, receipt_key=RECEIPT_KEY)
        options.update(changes)
        return verify_receipt_gated_recovery(**options)

    def test_valid_pair_accepted(self):
        self.assertTrue(self._verify())

    def test_missing_receipt_rejected(self):
        self.assertFalse(self._verify(trusted_receipt_path=self.receipt.with_name("missing")))

    def test_wrong_receipt_key_rejected(self):
        self.assertFalse(self._verify(receipt_key=b"z" * 32))

    def test_wrong_checkpoint_key_rejected(self):
        self.assertFalse(self._verify(checkpoint_key=b"z" * 32))

    def test_wrong_floor_key_rejected(self):
        self.assertFalse(self._verify(floor_key=b"z" * 32))

    def test_shared_keys_rejected(self):
        self.assertFalse(self._verify(receipt_key=FLOOR_KEY))

    def test_deleted_floor_rejected(self):
        next(self.floors.glob("floor-*.json")).unlink()
        self.assertFalse(self._verify())

    def test_corrupt_receipt_rejected(self):
        self.receipt.write_bytes(b"invalid")
        self.assertFalse(self._verify())

    def test_newer_floor_rejects_old_backup(self):
        self.store.append(self.case, "marker", {"n": 2})
        publish_recovery_floor(
            self.store, export_checkpoint(self.store, self.case, REVIEWERS),
            self.floors, FLOOR_KEY)
        newer = self.receipt.with_name("new-receipt.json")
        save_registry_receipt(
            export_registry_receipt(self.floors, FLOOR_KEY, RECEIPT_KEY), newer)
        self.assertFalse(self._verify(trusted_receipt_path=newer))

    def test_old_receipt_rejected_after_registry_advances(self):
        self.store.append(self.case, "marker", {"n": 2})
        publish_recovery_floor(
            self.store, export_checkpoint(self.store, self.case, REVIEWERS),
            self.floors, FLOOR_KEY)
        self.assertFalse(self._verify())

if __name__ == "__main__":
    unittest.main()
