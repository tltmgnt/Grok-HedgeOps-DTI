import sqlite3
import tempfile
import unittest
from pathlib import Path
from hedgeops.store import EventStore

class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "journal.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_survives_restart(self):
        with EventStore(self.path) as store:
            store.append("case-1", "prediction", {"target": 100})
            self.assertTrue(store.verify_chain())
        with EventStore(self.path) as store:
            self.assertEqual(store.history("case-1")[0]["payload"]["target"], 100)
            self.assertTrue(store.verify_chain())

    def test_stream_filter_and_order(self):
        with EventStore(self.path) as store:
            store.append("a", "prediction", {"x": 1})
            store.append("b", "measurement", {"x": 2})
            store.append("a", "review", {"x": 3})
            self.assertEqual([e["kind"] for e in store.history("a")],
                             ["prediction", "review"])

    def test_detects_payload_tampering(self):
        with EventStore(self.path) as store:
            store.append("a", "prediction", {"x": 1})
            store.db.execute("UPDATE events SET payload=? WHERE seq=1", ('{"x":99}',))
            store.db.commit()
            self.assertFalse(store.verify_chain())

    def test_rejects_invalid_event(self):
        with EventStore(self.path) as store:
            with self.assertRaises(ValueError):
                store.append("", "prediction", {})
            with self.assertRaises(ValueError):
                store.append("a", "prediction", float("nan"))

    def test_snapshot(self):
        with EventStore(self.path) as store:
            store.append("a", "prediction", {"x": 1})
            snap = store.snapshot("a")
            self.assertEqual(snap["event_count"], 1)
            self.assertTrue(snap["global_chain_valid"])

if __name__ == "__main__":
    unittest.main()
