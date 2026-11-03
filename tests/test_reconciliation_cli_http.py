"""Phase 71: CLI integration against real loopback custody HTTP."""
import contextlib
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hedgeops.custody_server import CustodyDatabase, make_handler
from hedgeops.https_custody import HTTPSExecutionCheckpointCustodian
from hedgeops.reconciliation_cli import main, EXIT_READY, EXIT_DENIED
from hedgeops.recovery_execution_checkpoint import create_execution_checkpoint
from hedgeops.recovery_execution_custody import execution_checkpoint_fingerprint
from hedgeops.recovery_fence import RecoveryFenceAuthority
from hedgeops.recovery_reconciliation_outbox import (
    execute_with_reconciliation_outbox, reconcile_pending_outbox)

TOKEN = "phase71-custody-bearer-token-long"
OPERATOR = "phase71-operator-token-long-enough"
KEY = b"k" * 32
URL = "https://custody.example.test/v1/execution-checkpoint"


class Response:
    def __init__(self, response, connection):
        self.response, self.connection = response, connection
        self.status = response.status
        self.headers = dict(response.getheaders())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.response.read()
        self.connection.close()

    def read(self, size=-1):
        return self.response.read(size)

    def geturl(self):
        return URL


class CountingOpener:
    def __init__(self, port):
        self.port = port
        self.methods = []

    def open(self, request, timeout):
        method = request.get_method()
        self.methods.append(method)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = dict(request.header_items())
        if method == "GET":
            conn.putrequest("GET", "/v1/execution-checkpoint")
            for name, value in headers.items():
                if name.lower() not in ("content-length", "transfer-encoding"):
                    conn.putheader(name, value)
            conn.endheaders()
        else:
            conn.request(method, "/v1/execution-checkpoint",
                         body=request.data, headers=headers)
        response = conn.getresponse()
        if response.status >= 400:
            status = response.status
            response.read()
            conn.close()
            raise urllib.error.HTTPError(URL, status, "local test", {}, None)
        return Response(response, conn)


class CLIHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.path = root / "fence.db"
        self.authority = RecoveryFenceAuthority(self.path, strict=True)
        generation = self.authority.acquire_authorized(
            "operator", OPERATOR, configured_token=OPERATOR)
        with patch("hedgeops.recovery_execution.verify_recovery_custody_gate",
                   return_value=True):
            execute_with_reconciliation_outbox(
                self.authority, None, None, None, None, None, None, None,
                generation, OPERATOR, lambda db: None,
                configured_token=OPERATOR)
        self.db = CustodyDatabase(root / "custody.db")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.db, TOKEN))
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.opener = CountingOpener(self.server.server_port)
        self.checkpoint = root / "checkpoint.json"
        self.checkpoint.write_text(json.dumps(
            create_execution_checkpoint(self.authority, KEY)), encoding="utf-8")
        self.args = ["--database", str(self.path),
                     "--checkpoint", str(self.checkpoint),
                     "--custody-url", URL]
        self.env = {"HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX": KEY.hex(),
                    "HEDGEOPS_CUSTODY_BEARER_TOKEN": TOKEN}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def run_cli(self):
        output = io.StringIO()
        original = HTTPSExecutionCheckpointCustodian
        opener = self.opener

        def client(url, token):
            return original(url, token, opener=opener)

        with patch.dict(os.environ, self.env), patch(
                "hedgeops.reconciliation_cli.HTTPSExecutionCheckpointCustodian",
                side_effect=client), contextlib.redirect_stdout(output):
            code = main(self.args)
        return code, json.loads(output.getvalue())

    def test_pending_denied_without_http_writes(self):
        code, report = self.run_cli()
        self.assertEqual(code, EXIT_DENIED)
        self.assertEqual(report["reason_code"], "PENDING_RECONCILIATION")
        self.assertEqual(self.opener.methods, [])
        self.assertIsNone(self.db.read_execution())

    def test_confirmed_ready_uses_get_only(self):
        publisher = HTTPSExecutionCheckpointCustodian(
            URL, TOKEN, opener=self.opener)
        reconcile_pending_outbox(self.authority, KEY, publisher)
        self.opener.methods.clear()
        before = self.db.read_execution()
        code, report = self.run_cli()
        self.assertEqual(code, EXIT_READY)
        self.assertEqual(report["reason_code"], "READY")
        self.assertTrue(self.opener.methods)
        self.assertEqual(set(self.opener.methods), {"GET"})
        self.assertEqual(self.db.read_execution(), before)

    def test_wrong_custody_digest_denied_without_put(self):
        checkpoint = create_execution_checkpoint(self.authority, KEY)
        self.db.cas_execution("*", {
            "sequence": checkpoint["sequence"],
            "checkpoint_sha256": "f" * 64})
        with self.authority._connect() as db:
            db.execute("UPDATE recovery_reconciliation_outbox SET confirmed=1")
        code, report = self.run_cli()
        self.assertEqual(code, EXIT_DENIED)
        self.assertEqual(report["reason_code"], "CUSTODY_UNVERIFIED")
        self.assertEqual(set(self.opener.methods), {"GET"})
        self.assertEqual(self.db.read_execution()["checkpoint_sha256"], "f" * 64)


if __name__ == "__main__":
    unittest.main()
