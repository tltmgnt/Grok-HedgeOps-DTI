"""Phase 44 fenced alert HTTP protocol regression tests."""
import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase, make_handler
from hedgeops.recovery_fence import RecoveryFenceAuthority

TOKEN = "phase44-test-only-operator-token"
RECORD = {"sequence": 1, "checkpoint_sha256": "a" * 64}


class FencedAlertProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "custody.sqlite3"
        self.db = CustodyDatabase(self.path)
        self.authority = RecoveryFenceAuthority(self.path)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(self.db, TOKEN, require_alert_fence=True))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def put(self, record=RECORD, fence=None, condition="*", extra=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=4)
        headers = {"Authorization": "Bearer " + TOKEN,
                   "If-None-Match" if condition == "*" else "If-Match": condition}
        if fence is not None:
            headers["X-Recovery-Fence"] = str(fence)
        if extra:
            headers.update(extra)
        conn.request("PUT", "/v1/alert-checkpoint",
                     body=json.dumps(record).encode(), headers=headers)
        response = conn.getresponse()
        status = response.status
        response.read()
        conn.close()
        return status

    def test_missing_fence_rejected(self):
        self.assertEqual(self.put(), 428)
        self.assertIsNone(self.db.read_alert())

    def test_current_fence_accepted(self):
        generation = self.authority.acquire()
        self.assertEqual(self.put(fence=generation), 204)
        self.assertEqual(self.db.read_alert(), RECORD)

    def test_stale_fence_rejected(self):
        stale = self.authority.acquire()
        self.authority.acquire()
        self.assertEqual(self.put(fence=stale), 412)
        self.assertIsNone(self.db.read_alert())

    def test_invalid_fences_rejected(self):
        self.authority.acquire()
        for bad in ("0", "-1", "01", "abc", "1.0", "9" * 30):
            with self.subTest(bad=bad):
                self.assertEqual(self.put(fence=bad), 428)

    def test_new_generation_allows_next_monotonic_write(self):
        first = self.authority.acquire()
        self.assertEqual(self.put(fence=first), 204)
        current = self.db.read_alert()
        import hashlib
        from hedgeops.store import canonical
        etag = '"' + hashlib.sha256(canonical(current).encode()).hexdigest() + '"'
        next_generation = self.authority.acquire()
        self.assertEqual(self.put(
            dict(RECORD, sequence=2), fence=first, condition=etag), 412)
        self.assertEqual(self.put(
            dict(RECORD, sequence=2), fence=next_generation, condition=etag), 204)

    def test_concurrent_same_generation_one_winner(self):
        generation = self.authority.acquire()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.put(fence=generation), range(2)))
        self.assertEqual(sorted(results), [204, 412])

    def test_fence_cannot_bypass_receipt_namespace(self):
        generation = self.authority.acquire()
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=4)
        conn.request("PUT", "/v1/receipt",
                     body=json.dumps({"sequence": 1, "receipt_sha256": "b" * 64}),
                     headers={"Authorization": "Bearer " + TOKEN,
                              "If-None-Match": "*",
                              "X-Recovery-Fence": str(generation)})
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        conn.close()

    def test_no_generation_fails_closed(self):
        self.assertEqual(self.put(fence=1), 412)

    def test_duplicate_fence_header_rejected(self):
        generation = self.authority.acquire()
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=4)
        conn.putrequest("PUT", "/v1/alert-checkpoint")
        conn.putheader("Authorization", "Bearer " + TOKEN)
        conn.putheader("If-None-Match", "*")
        conn.putheader("X-Recovery-Fence", str(generation))
        conn.putheader("X-Recovery-Fence", str(generation))
        raw = json.dumps(RECORD).encode()
        conn.putheader("Content-Length", str(len(raw)))
        conn.endheaders(raw)
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        conn.close()


if __name__ == "__main__":
    unittest.main()
