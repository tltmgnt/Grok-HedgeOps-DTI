"""Phase 35 bounded connection admission and slot-release regressions."""
import http.client
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from hedgeops.connection_server import BoundedCustodyHTTPServer
from hedgeops.custody_server import CustodyDatabase, make_handler

TOKEN = "test-only-bounded-connection-token"


class ConnectionAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db = CustodyDatabase(Path(self.temp.name) / "custody.sqlite3")
        self.server = BoundedCustodyHTTPServer(
            ("127.0.0.1", 0), make_handler(db, TOKEN),
            max_connections=1)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def _wait(self, predicate):
        for _ in range(100):
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for connection state")

    def _health(self):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=2)
        try:
            conn.putrequest("GET", "/v1/health")
            conn.putheader("Authorization", "Bearer " + TOKEN)
            conn.endheaders()
            response = conn.getresponse()
            status = response.status
            response.read()
            return status
        finally:
            conn.close()

    def test_saturated_connection_rejected_before_thread(self):
        idle = socket.create_connection(
            ("127.0.0.1", self.server.server_port), timeout=2)
        try:
            self._wait(lambda: self.server.active_connections == 1)
            second = socket.create_connection(
                ("127.0.0.1", self.server.server_port), timeout=2)
            try:
                self._wait(lambda: self.server.rejected_connections == 1)
                self.assertEqual(self.server.active_connections, 1)
                second.settimeout(2)
                self.assertEqual(second.recv(1), b"")
            finally:
                second.close()
        finally:
            idle.close()
        self._wait(lambda: self.server.active_connections == 0)
        self.assertEqual(self._health(), 200)

    def test_keepalive_holds_slot_until_disconnect(self):
        self.assertEqual(self._health(), 200)
        self._wait(lambda: self.server.active_connections == 0)

    def test_invalid_connection_limits(self):
        for limit in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                BoundedCustodyHTTPServer(
                    ("127.0.0.1", 0), make_handler(
                        CustodyDatabase(Path(self.temp.name) / "custody.sqlite3"),
                        TOKEN), max_connections=limit)

    def test_rejected_connection_count_is_observable(self):
        self.assertEqual(self.server.rejected_connections, 0)
        self.assertEqual(self._health(), 200)
        self.assertEqual(self.server.rejected_connections, 0)


if __name__ == "__main__":
    unittest.main()
