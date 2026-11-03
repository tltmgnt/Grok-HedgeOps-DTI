"""Phase 72: fail-closed CLI custody transport and protocol faults."""
import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from hedgeops.reconciliation_cli import EXIT_DENIED, EXIT_ERROR, main
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import execute_with_reconciliation_outbox
from hedgeops.https_custody import HTTPSExecutionCheckpointCustodian

TOKEN = "phase72-custody-bearer-token-long"
OPERATOR = "phase72-operator-token-long-enough"
KEY = b"k" * 32
URL = "https://custody.example.test/v1/execution-checkpoint"


class FakeResponse:
    status = 200
    def __init__(self, payload, etag='"validator"'):
        self.payload = payload
        self.headers = {"ETag": etag}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return URL

    def read(self, limit=-1):
        return self.payload[:limit]


class FaultOpener:
    def __init__(self, fault):
        self.fault = fault
        self.methods = []

    def open(self, request, timeout):
        self.methods.append(request.get_method())
        if isinstance(self.fault, Exception):
            raise self.fault
        return self.fault


class CLIFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = root / "fence.db"
        authority = RecoveryFenceAuthority(self.database, strict=True)
        generation = authority.acquire_authorized(
            "operator", OPERATOR, configured_token=OPERATOR)
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                authority, None, None, None, None, None, None, None,
                generation, OPERATOR, lambda db: None,
                configured_token=OPERATOR)
        with authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET confirmed=1")
        self.checkpoint = root / "checkpoint.json"
        self.checkpoint.write_text(json.dumps(
            create_execution_checkpoint(authority, KEY)), encoding="utf-8")
        self.args = ["--database", str(self.database),
                     "--checkpoint", str(self.checkpoint),
                     "--custody-url", URL]
        self.env = {"HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX": KEY.hex(),
                    "HEDGEOPS_CUSTODY_BEARER_TOKEN": TOKEN}

    def tearDown(self):
        self.temp.cleanup()

    def run_fault(self, fault):
        opener = FaultOpener(fault)
        output = io.StringIO()
        def factory(url, token):
            return HTTPSExecutionCheckpointCustodian(url, token, opener=opener)
        with patch.dict(os.environ, self.env), patch(
                "hedgeops.reconciliation_cli.HTTPSExecutionCheckpointCustodian",
                side_effect=factory), contextlib.redirect_stdout(output):
            code = main(self.args)
        report = json.loads(output.getvalue())
        self.assertFalse(report["ready"])
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertNotIn(KEY.hex(), output.getvalue())
        self.assertNotIn(URL, output.getvalue())
        self.assertEqual(set(opener.methods), {"GET"})
        return code, report

    def test_timeout_fails_closed(self):
        code, report = self.run_fault(TimeoutError("secret timeout"))
        self.assertIn(code, (EXIT_DENIED, EXIT_ERROR))
        self.assertNotEqual(report["reason_code"], "READY")

    def test_authentication_rejection_fails_closed(self):
        code, report = self.run_fault(
            urllib.error.HTTPError(URL, 401, "secret token", {}, None))
        self.assertIn(code, (EXIT_DENIED, EXIT_ERROR))
        self.assertNotEqual(report["reason_code"], "READY")

    def test_malformed_json_fails_closed(self):
        code, report = self.run_fault(FakeResponse(b"{bad-json"))
        self.assertEqual(code, EXIT_DENIED)
        self.assertEqual(report["reason_code"], "CUSTODY_UNVERIFIED")

    def test_missing_strong_etag_fails_closed(self):
        code, report = self.run_fault(FakeResponse(b"{}", etag='W/"weak"'))
        self.assertEqual(code, EXIT_DENIED)
        self.assertEqual(report["reason_code"], "CUSTODY_UNVERIFIED")

    def test_oversized_response_fails_closed(self):
        code, report = self.run_fault(FakeResponse(b"x" * 4097))
        self.assertEqual(code, EXIT_DENIED)
        self.assertEqual(report["reason_code"], "CUSTODY_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
