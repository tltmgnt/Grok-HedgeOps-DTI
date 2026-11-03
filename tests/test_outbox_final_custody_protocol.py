"""Phase 82 malformed final custody responses fail closed."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox,
    pending_reconciliations)
from hedgeops.recovery_execution_reconciliation import ExecutionReconciliationError

TOKEN = "phase82-operator-token-long-enough"
KEY = b"k" * 32


class FinalRead:
    def __init__(self, response):
        self.response = response
        self.reads = 0

    def read(self):
        self.reads += 1
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class FinalCustodyProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.authority = RecoveryFenceAuthority(
            Path(self.temp.name) / "fence.db", strict=True)
        generation = self.authority.acquire_authorized(
            "operator", TOKEN, configured_token=TOKEN)
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                generation, TOKEN, lambda db: None,
                configured_token=TOKEN)
        self.checkpoint = create_execution_checkpoint(self.authority, KEY)

    def tearDown(self):
        self.temp.cleanup()

    def test_malformed_final_responses_never_confirm(self):
        cases = [
            {"sequence": True, "checkpoint_sha256": "a" * 64},
            {"sequence": 1},
            {"sequence": 1, "checkpoint_sha256": "not-a-digest"},
            ["unexpected"],
            ValueError("invalid JSON"),
            TypeError("invalid payload"),
            KeyError("missing field"),
            UnicodeError("invalid encoding"),
            OSError("network timeout"),
        ]
        for response in cases:
            with self.subTest(response=repr(response)):
                custodian = FinalRead(response)
                with patch(
                    "hedgeops.recovery_reconciliation_outbox.reconcile_execution_custody",
                    return_value=self.checkpoint):
                    with self.assertRaises(ExecutionReconciliationError):
                        reconcile_pending_outbox(self.authority, KEY, custodian)
                self.assertEqual(custodian.reads, 1)
                self.assertEqual(
                    [entry["sequence"] for entry in
                     pending_reconciliations(self.authority)], [1])


if __name__ == "__main__":
    unittest.main()
