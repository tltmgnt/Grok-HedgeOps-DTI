"""Registry-head receipt and rollback regression tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.audit import export_checkpoint
from hedgeops.floor_registry import publish_recovery_floor
from hedgeops.identity import ReviewerRegistry
from hedgeops.registry_receipt import (
    export_registry_receipt, verify_registry_receipt,
    save_registry_receipt, load_registry_receipt)
from hedgeops.store import EventStore
from hedgeops.workflow import create_case

FLOOR_KEY = b"f" * 32
RECEIPT_KEY = b"r" * 32
REGISTRY = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class RegistryReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.directory = root / "floors"
        self.directory.mkdir()
        self.store = EventStore(root / "journal.sqlite3")
        self.case = create_case(self.store, "Pilot?", fake_agent)
        self.receipt_path = root / "trusted-receipt.json"
        self._publish()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _publish(self):
        publish_recovery_floor(
            self.store, export_checkpoint(self.store, self.case, REGISTRY),
            self.directory, FLOOR_KEY)

    def _receipt(self):
        return export_registry_receipt(self.directory, FLOOR_KEY, RECEIPT_KEY)

    def test_receipt_round_trip(self):
        receipt = self._receipt()
        save_registry_receipt(receipt, self.receipt_path)
        loaded = load_registry_receipt(self.receipt_path)
        self.assertEqual(receipt, loaded)
        self.assertTrue(verify_registry_receipt(
            self.directory, FLOOR_KEY, loaded, RECEIPT_KEY))

    def test_deleted_latest_record_detected(self):
        self.store.append(self.case, "marker", {"n": 2})
        self._publish()
        receipt = self._receipt()
        (self.directory / "floor-000000000002.json").unlink()
        self.assertFalse(verify_registry_receipt(
            self.directory, FLOOR_KEY, receipt, RECEIPT_KEY))

    def test_wrong_receipt_key_rejected(self):
        self.assertFalse(verify_registry_receipt(
            self.directory, FLOOR_KEY, self._receipt(), b"z" * 32))

    def test_receipt_tampering_rejected(self):
        receipt = self._receipt()
        receipt["sequence"] += 1
        self.assertFalse(verify_registry_receipt(
            self.directory, FLOOR_KEY, receipt, RECEIPT_KEY))

    def test_stale_receipt_rejected_after_advancement(self):
        receipt = self._receipt()
        self.store.append(self.case, "marker", {"n": 2})
        self._publish()
        self.assertFalse(verify_registry_receipt(
            self.directory, FLOOR_KEY, receipt, RECEIPT_KEY))

    def test_existing_receipt_cannot_be_overwritten(self):
        receipt = self._receipt()
        save_registry_receipt(receipt, self.receipt_path)
        with self.assertRaises(FileExistsError):
            save_registry_receipt(receipt, self.receipt_path)

    def test_invalid_receipt_file_rejected(self):
        self.receipt_path.write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            load_registry_receipt(self.receipt_path)

    def test_short_receipt_key_rejected(self):
        with self.assertRaises(ValueError):
            export_registry_receipt(self.directory, FLOOR_KEY, b"short")

if __name__ == "__main__":
    unittest.main()
