"""Recovery-floor registry publication and retrieval regressions."""
import tempfile
import unittest
from pathlib import Path

from hedgeops.audit import export_checkpoint
from hedgeops.floor_registry import latest_recovery_floor, publish_recovery_floor
from hedgeops.identity import ReviewerRegistry
from hedgeops.store import EventStore
from hedgeops.workflow import create_case

KEY = b"r" * 32
REGISTRY = ReviewerRegistry({"alice": ("approver", b"a" * 32)})

def fake_agent(system, problem):
    return {"hypothesis": "Pilot", "evidence": [],
            "assumptions": ["Capacity"], "risks": ["Delay"],
            "falsification_tests": ["Measure"], "confidence": "unknown"}

class FloorRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.directory = root / "floors"
        self.directory.mkdir()
        self.store = EventStore(root / "journal.sqlite3")
        self.case = create_case(self.store, "Pilot?", fake_agent)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _checkpoint(self):
        return export_checkpoint(self.store, self.case, REGISTRY)

    def test_publish_and_read_latest(self):
        floor = publish_recovery_floor(self.store, self._checkpoint(),
                                      self.directory, KEY)
        self.assertEqual(latest_recovery_floor(self.directory, KEY), floor)

    def test_advancing_floor(self):
        first = publish_recovery_floor(self.store, self._checkpoint(),
                                       self.directory, KEY)
        self.store.append(self.case, "test_marker", {"step": 2})
        second = publish_recovery_floor(self.store, self._checkpoint(),
                                        self.directory, KEY)
        self.assertGreater(second["minimum_event_count"], first["minimum_event_count"])
        self.assertEqual(latest_recovery_floor(self.directory, KEY), second)

    def test_same_position_cannot_be_republished(self):
        publish_recovery_floor(self.store, self._checkpoint(), self.directory, KEY)
        with self.assertRaises(ValueError):
            publish_recovery_floor(self.store, self._checkpoint(), self.directory, KEY)

    def test_wrong_key_rejected(self):
        publish_recovery_floor(self.store, self._checkpoint(), self.directory, KEY)
        with self.assertRaises(ValueError):
            latest_recovery_floor(self.directory, b"z" * 32)

    def test_record_tampering_rejected(self):
        publish_recovery_floor(self.store, self._checkpoint(), self.directory, KEY)
        path = next(self.directory.glob("floor-*.json"))
        path.write_text(path.read_text().replace("GENESIS", "ALTERED"), encoding="utf-8")
        with self.assertRaises(ValueError):
            latest_recovery_floor(self.directory, KEY)

    def test_missing_intermediate_record_rejected(self):
        publish_recovery_floor(self.store, self._checkpoint(), self.directory, KEY)
        self.store.append(self.case, "test_marker", {"step": 2})
        publish_recovery_floor(self.store, self._checkpoint(), self.directory, KEY)
        (self.directory / "floor-000000000001.json").unlink()
        with self.assertRaises(ValueError):
            latest_recovery_floor(self.directory, KEY)

    def test_empty_registry_rejected(self):
        with self.assertRaises(ValueError):
            latest_recovery_floor(self.directory, KEY)

    def test_stale_checkpoint_rejected(self):
        old = self._checkpoint()
        self.store.append(self.case, "test_marker", {"step": 2})
        with self.assertRaises(ValueError):
            publish_recovery_floor(self.store, old, self.directory, KEY)

if __name__ == "__main__":
    unittest.main()
