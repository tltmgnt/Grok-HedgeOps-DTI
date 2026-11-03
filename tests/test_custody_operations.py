"""Operational custody health, timeout and fail-closed error regressions."""
import http.client
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hedgeops.custody_server import (
    CustodyDatabase, REQUEST_TIMEOUT_SECONDS, make_handler,
)

TOKEN = "test-only-operational-custody-token"
FIRST = {"sequence": 1, "receipt_sha256": "a" * 64}


class OperationalCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = CustodyDatabase(Path(self.temp.name) / "custody.sqlite3")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.database, TOKEN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, path, token=TOKEN):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        conn.putrequest("GET", path)
        conn.putheader("Authorization", "Bearer " + token)
        conn.endheaders()
        response = conn.getresponse()
        status = response.status
        response.read()
        conn.close()
        return status

    def test_authenticated_healthy_database(self):
        self.assertEqual(self.request("/v1/health"), 200)

    def test_health_requires_authorization(self):
        self.assertEqual(self.request("/v1/health", "wrong"), 401)

    def test_failed_integrity_check_reports_unavailable(self):
        with patch.object(self.database, "healthy", return_value=False):
            self.assertEqual(self.request("/v1/health"), 503)

    def test_database_read_failure_reports_unavailable(self):
        with patch.object(self.database, "read",
                          side_effect=sqlite3.OperationalError("private database path")):
            self.assertEqual(self.request("/v1/receipt"), 503)

    def test_database_health_failure_reports_unavailable(self):
        with patch.object(self.database, "healthy",
                          side_effect=sqlite3.DatabaseError("private details")):
            self.assertEqual(self.request("/v1/health"), 503)

    def test_write_failure_reports_unavailable_and_no_mutation(self):
        import json
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        with patch.object(self.database, "cas",
                          side_effect=sqlite3.OperationalError("private details")):
            conn.request("PUT", "/v1/receipt", body=json.dumps(FIRST).encode(),
                         headers={"Authorization": "Bearer " + TOKEN,
                                  "If-None-Match": "*"})
            response = conn.getresponse()
            self.assertEqual(response.status, 503)
            self.assertNotIn(b"private", response.read())
        conn.close()
        self.assertIsNone(self.database.read())

    def test_request_timeout_is_bounded(self):
        self.assertGreater(REQUEST_TIMEOUT_SECONDS, 0)
        self.assertLessEqual(REQUEST_TIMEOUT_SECONDS, 10)


if __name__ == "__main__":
    unittest.main()
