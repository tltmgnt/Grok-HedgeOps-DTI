"""Phase 36 security counter correctness and secret minimization tests."""
import http.client
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.custody_metrics import CustodyMetrics
from hedgeops.custody_server import CustodyDatabase, make_handler

TOKEN = "test-only-security-metrics-token"


class SecurityMetricsTests(unittest.TestCase):
    def test_counter_aggregation(self):
        metrics = CustodyMetrics()
        metrics.record("GET", "health", 200)
        metrics.record("GET", "health", 200)
        self.assertEqual(metrics.snapshot(), [
            {"method": "GET", "route": "health", "status": 200, "count": 2}])

    def test_reject_unbounded_dimensions(self):
        metrics = CustodyMetrics()
        for args in (("DELETE", "health", 200),
                     ("GET", "secret-path", 200),
                     ("GET", "health", 999)):
            with self.assertRaises(ValueError):
                metrics.record(*args)

    def test_snapshot_is_detached(self):
        metrics = CustodyMetrics()
        metrics.record("GET", "health", 200)
        metrics.snapshot()[0]["count"] = 999
        self.assertEqual(metrics.snapshot()[0]["count"], 1)

    def test_concurrent_updates(self):
        metrics = CustodyMetrics()
        workers = [threading.Thread(
            target=lambda: [metrics.record("PUT", "receipt", 412)
                            for _ in range(100)]) for _ in range(5)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=3)
        self.assertEqual(metrics.snapshot()[0]["count"], 500)

    def test_http_outcomes_without_sensitive_data(self):
        with tempfile.TemporaryDirectory() as directory:
            db = CustodyDatabase(Path(directory) / "custody.sqlite3")
            metrics = CustodyMetrics()
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0),
                make_handler(db, TOKEN, metrics=metrics))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for token, expected in ((TOKEN, 200), ("wrong-token", 401)):
                    conn = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=3)
                    conn.putrequest("GET", "/v1/health")
                    conn.putheader("Authorization", "Bearer " + token)
                    conn.endheaders()
                    response = conn.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    conn.close()
                snapshot = metrics.snapshot()
                self.assertEqual(len(snapshot), 2)
                self.assertEqual({row["status"] for row in snapshot}, {200, 401})
                self.assertNotIn(TOKEN, str(snapshot))
                self.assertNotIn("wrong-token", str(snapshot))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
