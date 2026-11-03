"""Phase 70 CLI JSON, exit code and read-only regression tests."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hedgeops.reconciliation_cli import (
    EXIT_DENIED, EXIT_ERROR, EXIT_READY, ReadOnlyAuthority, main)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.checkpoint = Path(self.temp.name) / "checkpoint.json"
        self.checkpoint.write_text(json.dumps({"sequence": 1}), encoding="utf-8")
        self.args = ["--database", str(Path(self.temp.name) / "fence.db"),
                     "--checkpoint", str(self.checkpoint),
                     "--custody-url", "https://example.org/v1/execution-checkpoint"]
        self.environment = {
            "HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX": "6b" * 32,
            "HEDGEOPS_CUSTODY_BEARER_TOKEN": "phase70-custody-bearer-token-long",
        }

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, report):
        output = io.StringIO()
        with patch.dict(os.environ, self.environment), patch(
                "hedgeops.reconciliation_cli.readiness_diagnostics",
                return_value=report), contextlib.redirect_stdout(output):
            code = main(self.args)
        return code, json.loads(output.getvalue())

    def test_ready_exit_and_json(self):
        code, report = self.run_cli({"ready": True, "reason_code": "READY"})
        self.assertEqual(code, EXIT_READY)
        self.assertEqual(report["reason_code"], "READY")

    def test_denied_exit_and_json(self):
        code, report = self.run_cli({
            "ready": False, "reason_code": "PENDING_RECONCILIATION"})
        self.assertEqual(code, EXIT_DENIED)
        self.assertEqual(report["reason_code"], "PENDING_RECONCILIATION")

    def test_missing_environment_fails_without_secret_leak(self):
        output = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(output):
            code = main(self.args)
        self.assertEqual(code, EXIT_ERROR)
        report = json.loads(output.getvalue())
        self.assertEqual(report["reason_code"], "READINESS_UNAVAILABLE")
        self.assertNotIn("HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX",
                         output.getvalue())

    def test_readonly_authority_does_not_create_database(self):
        path = Path(self.temp.name) / "nonexistent.db"
        with self.assertRaises(Exception):
            with ReadOnlyAuthority(path)._connect() as db:
                db.execute("SELECT 1")
        self.assertFalse(path.exists())

    def test_invalid_hex_fails_closed(self):
        output = io.StringIO()
        with patch.dict(os.environ, dict(
                self.environment,
                HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX="not-hex"
                )), contextlib.redirect_stdout(output):
            code = main(self.args)
        self.assertEqual(code, EXIT_ERROR)
        self.assertFalse(json.loads(output.getvalue())["ready"])


if __name__ == "__main__":
    unittest.main()
