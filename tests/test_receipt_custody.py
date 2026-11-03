"""Receipt custody CAS and recovery enforcement tests."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.audit import export_checkpoint
from hedgeops.backup import backup_with_checkpoint
from hedgeops.floor_registry import publish_recovery_floor
from hedgeops.identity import ReviewerRegistry
from hedgeops.receipt_custody import (
    CustodyError, publish_receipt_to_custodian,
    trusted_receipt_fingerprint, verify_custodied_recovery)
from hedgeops.registry_receipt import export_registry_receipt, save_registry_receipt
from hedgeops.store import EventStore
from hedgeops.workflow import create_case

CHECKPOINT_KEY = b"c" * 32
FLOOR_KEY = b"f" * 32
RECEIPT_KEY = b"r" * 32
REVIEWERS = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

class FakeCustodian:
    """Test-only CAS store; not independent durable custody."""
    def __init__(self):
        self.value = None
        self.conflict = False

    def read(self):
        return None if self.value is None else dict(self.value)

    def compare_and_swap(self, expected, new):
        if self.conflict or self.value != expected:
            return False
        self.value = dict(new)
        return True

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class ReceiptCustodyTests(unittest.TestCase):
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
        self.custodian = FakeCustodian()
        backup_with_checkpoint(self.store, self.case, REVIEWERS, self.backup,
                               self.checkpoint, authentication_key=CHECKPOINT_KEY)
        self._publish(self.receipt)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _publish(self, path):
        publish_recovery_floor(
            self.store, export_checkpoint(self.store, self.case, REVIEWERS),
            self.floors, FLOOR_KEY)
        save_registry_receipt(
            export_registry_receipt(self.floors, FLOOR_KEY, RECEIPT_KEY), path)

    def _custody_publish(self, path=None):
        return publish_receipt_to_custodian(
            self.floors, path or self.receipt, FLOOR_KEY, RECEIPT_KEY,
            self.custodian)

    def _verify(self):
        return verify_custodied_recovery(
            self.backup, self.checkpoint, REVIEWERS, self.floors,
            self.receipt, self.custodian,
            checkpoint_key=CHECKPOINT_KEY, floor_key=FLOOR_KEY,
            receipt_key=RECEIPT_KEY)

    def test_missing_custody_fails_closed(self):
        self.assertFalse(self._verify())
        with self.assertRaises(CustodyError):
            trusted_receipt_fingerprint(self.custodian)

    def test_publish_then_recover(self):
        record = self._custody_publish()
        self.assertEqual(trusted_receipt_fingerprint(self.custodian),
                         record["receipt_sha256"])
        self.assertTrue(self._verify())

    def test_republishing_same_sequence_rejected(self):
        self._custody_publish()
        with self.assertRaises(CustodyError):
            self._custody_publish()

    def test_cas_conflict_rejected(self):
        self.custodian.conflict = True
        with self.assertRaises(CustodyError):
            self._custody_publish()

    def test_malformed_custody_rejected(self):
        self.custodian.value = {"sequence": True, "receipt_sha256": "0" * 64}
        self.assertFalse(self._verify())

    def test_old_receipt_rejected_after_custody_advances(self):
        self._custody_publish()
        self.store.append(self.case, "marker", {"n": 2})
        newer = self.receipt.with_name("new-receipt.json")
        self._publish(newer)
        self._custody_publish(newer)
        self.assertFalse(self._verify())

    def test_custody_rollback_rejected_on_publication(self):
        self._custody_publish()
        self.store.append(self.case, "marker", {"n": 2})
        newer = self.receipt.with_name("new-receipt.json")
        self._publish(newer)
        self._custody_publish(newer)
        # The old receipt is no longer the registry head.
        with self.assertRaises(CustodyError):
            self._custody_publish(self.receipt)

    def test_replaced_custody_fingerprint_rejects(self):
        self._custody_publish()
        self.custodian.value["receipt_sha256"] = "0" * 64
        self.assertFalse(self._verify())

if __name__ == "__main__":
    unittest.main()
