"""Phase 46 persisted strict issuance policy tests."""
import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase46-operator-token-long-enough"


class StrictFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_strict_rejects_legacy_acquire(self):
        authority = RecoveryFenceAuthority(self.path, strict=True)
        with self.assertRaises(PermissionError):
            authority.acquire()
        self.assertIsNone(authority.current())

    def test_authorized_issuance_still_works(self):
        authority = RecoveryFenceAuthority(self.path, strict=True)
        self.assertEqual(authority.acquire_authorized(
            "operator-1", TOKEN, configured_token=TOKEN), 1)
        self.assertTrue(authority.verify_issuance_audit())

    def test_policy_persists_across_reopen(self):
        RecoveryFenceAuthority(self.path, strict=True)
        legacy = RecoveryFenceAuthority(self.path)
        with self.assertRaises(PermissionError):
            legacy.acquire()

    def test_legacy_database_can_upgrade(self):
        legacy = RecoveryFenceAuthority(self.path)
        self.assertEqual(legacy.acquire(), 1)
        strict = RecoveryFenceAuthority(self.path, strict=True)
        with self.assertRaises(PermissionError):
            legacy.acquire()
        self.assertEqual(strict.acquire_authorized(
            "operator-1", TOKEN, configured_token=TOKEN), 2)

    def test_reopen_cannot_downgrade(self):
        RecoveryFenceAuthority(self.path, strict=True)
        RecoveryFenceAuthority(self.path, strict=False)
        with self.assertRaises(PermissionError):
            RecoveryFenceAuthority(self.path).acquire()

    def test_invalid_strict_type(self):
        with self.assertRaises(ValueError):
            RecoveryFenceAuthority(self.path, strict=1)

    def test_invalid_operator_token_still_denied(self):
        authority = RecoveryFenceAuthority(self.path, strict=True)
        with self.assertRaises(PermissionError):
            authority.acquire_authorized(
                "operator-1", "invalid", configured_token=TOKEN)
        self.assertIsNone(authority.current())

    def test_concurrent_legacy_bypass_denied(self):
        RecoveryFenceAuthority(self.path, strict=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            def attempt(_):
                try:
                    RecoveryFenceAuthority(self.path).acquire()
                except PermissionError:
                    return "denied"
                return "bypassed"
            results = list(pool.map(attempt, range(10)))
        self.assertEqual(results, ["denied"] * 10)

    def test_strict_policy_stored_in_database(self):
        RecoveryFenceAuthority(self.path, strict=True)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute(
                "SELECT strict FROM recovery_fence_policy WHERE id=1").fetchone(),
                (1,))

    def test_legacy_mode_remains_compatible(self):
        authority = RecoveryFenceAuthority(self.path)
        self.assertEqual(authority.acquire(), 1)
        self.assertEqual(authority.acquire(), 2)


if __name__ == "__main__":
    unittest.main()
