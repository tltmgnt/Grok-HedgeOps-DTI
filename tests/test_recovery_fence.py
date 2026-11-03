"""Phase 43 fencing generation and transactional stale-writer tests."""
import concurrent.futures
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority, StaleRecoveryFence


class RecoveryFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.sqlite3"
        self.authority = RecoveryFenceAuthority(self.path)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE guarded_state (value TEXT NOT NULL)")

    def tearDown(self):
        self.temp.cleanup()

    def test_first_generation(self):
        self.assertEqual(self.authority.acquire(), 1)

    def test_generation_increases(self):
        self.assertEqual([self.authority.acquire() for _ in range(3)],
                         [1, 2, 3])

    def test_reopen_preserves_generation(self):
        self.authority.acquire()
        self.assertEqual(RecoveryFenceAuthority(self.path).current(), 1)

    def test_stale_generation_rejected(self):
        first = self.authority.acquire()
        self.authority.acquire()
        with self.assertRaises(StaleRecoveryFence):
            self.authority.require_current(first)

    def test_invalid_generation_rejected(self):
        self.authority.acquire()
        for invalid in (True, 0, -1, "1", 1.5, None):
            with self.assertRaises(StaleRecoveryFence):
                self.authority.require_current(invalid)

    def test_guarded_update_commits(self):
        generation = self.authority.acquire()
        self.authority.guarded_update(
            generation, lambda db: db.execute(
                "INSERT INTO guarded_state VALUES ('accepted')"))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT value FROM guarded_state").fetchone()[0], "accepted")

    def test_stale_guarded_update_does_not_commit(self):
        old = self.authority.acquire()
        self.authority.acquire()
        with self.assertRaises(StaleRecoveryFence):
            self.authority.guarded_update(
                old, lambda db: db.execute(
                    "INSERT INTO guarded_state VALUES ('stale')"))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM guarded_state").fetchone()[0], 0)

    def test_callback_failure_rolls_back(self):
        generation = self.authority.acquire()
        def fail(db):
            db.execute("INSERT INTO guarded_state VALUES ('uncommitted')")
            raise RuntimeError("abort")
        with self.assertRaises(RuntimeError):
            self.authority.guarded_update(generation, fail)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM guarded_state").fetchone()[0], 0)

    def test_concurrent_acquire_unique(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            generations = list(pool.map(
                lambda _: self.authority.acquire(), range(12)))
        self.assertEqual(sorted(generations), list(range(1, 13)))

    def test_guarded_mutation_serializes_with_acquire(self):
        old = self.authority.acquire()
        entered = threading.Event()
        release = threading.Event()
        outcomes = []
        def update():
            def callback(db):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test synchronization timeout")
                db.execute("INSERT INTO guarded_state VALUES ('winner')")
            self.authority.guarded_update(old, callback)
            outcomes.append("committed")
        worker = threading.Thread(target=update)
        worker.start()
        self.assertTrue(entered.wait(3))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.authority.acquire)
            release.set()
            self.assertEqual(future.result(timeout=5), 2)
        worker.join(timeout=3)
        self.assertEqual(outcomes, ["committed"])
        with self.assertRaises(StaleRecoveryFence):
            self.authority.require_current(old)

    def test_read_only_check_is_not_a_commit_guard(self):
        generation = self.authority.acquire()
        self.assertTrue(self.authority.require_current(generation))
        self.authority.acquire()
        with self.assertRaises(StaleRecoveryFence):
            self.authority.guarded_update(generation, lambda db: None)


if __name__ == "__main__":
    unittest.main()
