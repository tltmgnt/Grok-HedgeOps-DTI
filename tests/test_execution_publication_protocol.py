"""Phase 83 publication-stage custody protocol failure regressions."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, pending_reconciliations)
from hedgeops.recovery_execution_reconciliation import (
    ExecutionReconciliationError, reconcile_execution_custody)

TOKEN = "phase83-operator-token-long-enough"
KEY = b"k" * 32


class FaultCustody:
    def __init__(self, stage, fault):
        self.stage = stage
        self.fault = fault
        self.reads = 0
        self.writes = 0
        self.record = None

    def read(self):
        self.reads += 1
        if (self.stage == "initial" and self.reads == 1 or
                self.stage == "confirmation" and self.reads == 2):
            if isinstance(self.fault, Exception):
                raise self.fault
            return self.fault
        return self.record

    def compare_and_swap(self, expected, record):
        self.writes += 1
        if self.stage == "cas":
            raise self.fault
        self.record = dict(record)
        return True


class PublicationProtocolTests(unittest.TestCase):
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

    def tearDown(self):
        self.temp.cleanup()

    def test_read_and_cas_protocol_failures_leave_outbox_pending(self):
        scenarios = [
            ("initial", {"sequence": 1}),
            ("initial", ["invalid"]),
            ("initial", ValueError("invalid JSON")),
            ("initial", TypeError("bad type")),
            ("initial", KeyError("missing")),
            ("initial", UnicodeError("encoding")),
            ("cas", ValueError("invalid CAS reply")),
            ("cas", TypeError("invalid CAS reply")),
            ("cas", KeyError("missing CAS field")),
            ("confirmation", ValueError("invalid JSON")),
            ("confirmation", TypeError("bad response")),
            ("confirmation", {"sequence": 1}),
        ]
        for stage, fault in scenarios:
            with self.subTest(stage=stage, fault=repr(fault)):
                custodian = FaultCustody(stage, fault)
                with self.assertRaises(ExecutionReconciliationError):
                    reconcile_execution_custody(self.authority, KEY, custodian)
                self.assertEqual(
                    [row["sequence"] for row in
                     pending_reconciliations(self.authority)], [1])


if __name__ == "__main__":
    unittest.main()
