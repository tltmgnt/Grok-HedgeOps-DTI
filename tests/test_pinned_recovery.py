"""Pinned receipt recovery tests with independent expected fingerprints."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.audit import export_checkpoint
from hedgeops.backup import backup_with_checkpoint
from hedgeops.floor_registry import publish_recovery_floor
from hedgeops.identity import ReviewerRegistry
from hedgeops.pinned_recovery import receipt_fingerprint, verify_pinned_recovery
from hedgeops.registry_receipt import (
    export_registry_receipt, save_registry_receipt, load_registry_receipt)
from hedgeops.store import EventStore
from hedgeops.workflow import create_case

CHECKPOINT_KEY = b"c" * 32
FLOOR_KEY = b"f" * 32
RECEIPT_KEY = b"r" * 32
REVIEWERS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class PinnedRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = EventStore(root / "live.sqlite3")
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.backup = root / "backup.sqlite3"
        self.checkpoint = root / "checkpoint.json"
        self.floors = root / "floors"
        self.floors.mkdir()
        self.receipt = root / "receipt.json"
        backup_with_checkpoint(
            self.store, self.case, REVIEWERS, self.backup, self.checkpoint,
            authentication_key=CHECKPOINT_KEY)
        self._publish(self.receipt)
        self.pin = receipt_fingerprint(load_registry_receipt(self.receipt))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _publish(self, path):
        publish_recovery_floor(
            self.store, export_checkpoint(self.store, self.case, REVIEWERS),
            self.floors, FLOOR_KEY)
        save_registry_receipt(
            export_registry_receipt(self.floors, FLOOR_KEY, RECEIPT_KEY), path)

    def _verify(self, **changes):
        options = dict(
            backup_path=self.backup, checkpoint_path=self.checkpoint,
            reviewer_registry=REVIEWERS, floor_directory=self.floors,
            trusted_receipt_path=self.receipt, expected_receipt_sha256=self.pin,
            checkpoint_key=CHECKPOINT_KEY, floor_key=FLOOR_KEY,
            receipt_key=RECEIPT_KEY)
        options.update(changes)
        return verify_pinned_recovery(**options)

    def test_matching_independent_pin_accepts(self):
        self.assertTrue(self._verify())

    def test_wrong_pin_rejected(self):
        self.assertFalse(self._verify(expected_receipt_sha256="0" * 64))

    def test_malformed_pin_rejected(self):
        self.assertFalse(self._verify(expected_receipt_sha256="not-a-hash"))
        self.assertFalse(self._verify(expected_receipt_sha256=None))

    def test_older_valid_receipt_and_registry_rejected_by_new_pin(self):
        old_receipt = load_registry_receipt(self.receipt)
        old_pin = receipt_fingerprint(old_receipt)
        self.store.append(self.case, "marker", {"n": 2})
        new_receipt = self.receipt.with_name("new-receipt.json")
        self._publish(new_receipt)
        new_pin = receipt_fingerprint(load_registry_receipt(new_receipt))
        self.assertNotEqual(old_pin, new_pin)
        # Old pair can still pass if old registry is restored. Pin rejects it.
        (self.floors / "floor-000000000002.json").unlink()
        self.assertFalse(self._verify(expected_receipt_sha256=new_pin))
        self.assertTrue(self._verify(expected_receipt_sha256=old_pin))

    def test_substituted_receipt_rejected(self):
        self.store.append(self.case, "marker", {"n": 2})
        newer = self.receipt.with_name("new-receipt.json")
        self._publish(newer)
        self.assertFalse(self._verify(trusted_receipt_path=newer))

    def test_missing_receipt_rejected(self):
        self.assertFalse(self._verify(trusted_receipt_path=self.receipt.with_name("missing")))

if __name__ == "__main__":
    unittest.main()
