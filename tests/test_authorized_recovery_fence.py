"""Phase 45 operator-authenticated fencing issuance tests."""
import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase45-test-operator-token-very-long"


class AuthorizedFenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "fence.sqlite3"
        self.authority = RecoveryFenceAuthority(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def issue(self, operator="operator-1", token=TOKEN):
        return self.authority.acquire_authorized(
            operator, token, configured_token=TOKEN)

    def test_authorized_issuance(self):
        self.assertEqual(self.issue(), 1)
        self.assertEqual(self.authority.current(), 1)
        self.assertTrue(self.authority.verify_issuance_audit())

    def test_invalid_token_denied_without_advancing(self):
        with self.assertRaises(PermissionError):
            self.issue(token="invalid")
        self.assertIsNone(self.authority.current())

    def test_empty_token_denied(self):
        with self.assertRaises(PermissionError):
            self.issue(token="")
        self.assertIsNone(self.authority.current())

    def test_invalid_operator_denied(self):
        for operator in ("", "../operator", "bad operator", "x" * 81):
            with self.subTest(operator=operator):
                with self.assertRaises(ValueError):
                    self.issue(operator=operator)
        self.assertIsNone(self.authority.current())

    def test_sequential_audit_chain(self):
        self.assertEqual([self.issue() for _ in range(3)], [1, 2, 3])
        self.assertTrue(self.authority.verify_issuance_audit())

    def test_concurrent_issuance_unique(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            generations = list(pool.map(lambda _: self.issue(), range(8)))
        self.assertEqual(sorted(generations), list(range(1, 9)))
        self.assertTrue(self.authority.verify_issuance_audit())

    def test_audit_tampering_detected(self):
        self.issue()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE recovery_fence_issuance SET event_hash=?",
                       ("0" * 64,))
        self.assertFalse(self.authority.verify_issuance_audit())

    def test_operator_identifier_not_stored_in_plaintext(self):
        self.issue("alice@example.com")
        with sqlite3.connect(self.path) as db:
            row = db.execute(
                "SELECT operator_digest FROM recovery_fence_issuance").fetchone()
        self.assertEqual(len(row[0]), 64)
        self.assertNotIn("alice", row[0])

    def test_reopen_audit(self):
        self.issue()
        self.assertTrue(
            RecoveryFenceAuthority(self.path).verify_issuance_audit())

    def test_legacy_acquire_still_available(self):
        self.assertEqual(self.authority.acquire(), 1)
        self.assertEqual(self.issue(), 2)
        self.assertTrue(self.authority.verify_issuance_audit())


if __name__ == "__main__":
    unittest.main()
