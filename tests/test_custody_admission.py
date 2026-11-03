"""Phase 34 admission limits and HTTP rate-limit regression tests."""
import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.admission import AdmissionController
from hedgeops.custody_server import CustodyDatabase, make_handler

TOKEN = "test-only-admission-bearer-token"


class AdmissionTests(unittest.TestCase):
    def test_per_peer_limit_and_window_reset(self):
        now = [100.0]
        gate = AdmissionController(requests_per_window=2, window_seconds=10,
                                   clock=lambda: now[0])
        for _ in range(2):
            self.assertEqual(gate.enter("peer"), "ok")
            gate.leave()
        self.assertEqual(gate.enter("peer"), "rate")
        self.assertEqual(gate.enter("other"), "ok")
        gate.leave()
        now[0] += 10
        self.assertEqual(gate.enter("peer"), "ok")
        gate.leave()

    def test_concurrency_limit(self):
        gate = AdmissionController(max_inflight=1)
        self.assertEqual(gate.enter("peer"), "ok")
        self.assertEqual(gate.enter("other"), "busy")
        gate.leave()
        self.assertEqual(gate.enter("other"), "ok")
        gate.leave()

    def test_invalid_limits_rejected(self):
        for options in ({"requests_per_window": 0},
                        {"max_inflight": 0}, {"window_seconds": 0},
                        {"requests_per_window": True}):
            with self.assertRaises(ValueError):
                AdmissionController(**options)

    def test_concurrent_limit_atomic(self):
        gate = AdmissionController(max_inflight=1)
        barrier = threading.Barrier(3)
        outcomes = []
        def enter():
            barrier.wait(timeout=3)
            outcomes.append(gate.enter("peer"))
        workers = [threading.Thread(target=enter) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait(timeout=3)
        for worker in workers:
            worker.join(timeout=3)
        self.assertEqual(sorted(outcomes), ["busy", "ok"])
        gate.leave()

    def test_http_rate_limit_before_database_access(self):
        with tempfile.TemporaryDirectory() as directory:
            db = CustodyDatabase(Path(directory) / "custody.sqlite3")
            gate = AdmissionController(requests_per_window=1)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(db, TOKEN, admission=gate))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                statuses = []
                for _ in range(2):
                    conn = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=3)
                    conn.putrequest("GET", "/v1/health")
                    conn.putheader("Authorization", "Bearer " + TOKEN)
                    conn.endheaders()
                    response = conn.getresponse()
                    statuses.append(response.status)
                    response.read()
                    conn.close()
                self.assertEqual(statuses, [200, 429])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
