"""Phase 41 namespaced custody protocol regression tests."""
import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase, make_handler
from hedgeops.https_custody import HTTPSAlertCheckpointCustodian

TOKEN = "test-only-alert-custody-token"
RECEIPT = {"sequence": 1, "receipt_sha256": "a" * 64}
ALERT = {"sequence": 1, "checkpoint_sha256": "b" * 64}


class NamespacedCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = CustodyDatabase(Path(self.temp.name) / "custody.sqlite3")
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.db, TOKEN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, method, path, record=None, condition=None, token=TOKEN):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + token}
        if condition is not None:
            headers["If-None-Match" if condition == "*" else "If-Match"] = condition
        data = json.dumps(record).encode() if record is not None else None
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        status, etag, raw = response.status, response.getheader("ETag"), response.read()
        connection.close()
        return status, etag, json.loads(raw) if raw else None

    def test_alert_endpoint_roundtrip(self):
        self.assertEqual(self.request("GET", "/v1/alert-checkpoint")[0], 404)
        self.assertEqual(self.request("PUT", "/v1/alert-checkpoint", ALERT, "*")[0], 204)
        self.assertEqual(self.request("GET", "/v1/alert-checkpoint")[2], ALERT)

    def test_receipt_namespace_unaffected(self):
        self.request("PUT", "/v1/alert-checkpoint", ALERT, "*")
        self.assertEqual(self.request("GET", "/v1/receipt")[0], 404)
        self.assertEqual(self.request("PUT", "/v1/receipt", RECEIPT, "*")[0], 204)
        self.assertEqual(self.request("GET", "/v1/receipt")[2], RECEIPT)

    def test_cross_namespace_schema_rejected(self):
        self.assertEqual(self.request("PUT", "/v1/alert-checkpoint", RECEIPT, "*")[0], 400)
        self.assertEqual(self.request("PUT", "/v1/receipt", ALERT, "*")[0], 400)

    def test_alert_requires_authorization(self):
        self.assertEqual(self.request("GET", "/v1/alert-checkpoint", token="wrong")[0], 401)

    def test_alert_cas_monotonic(self):
        self.request("PUT", "/v1/alert-checkpoint", ALERT, "*")
        _, etag, _ = self.request("GET", "/v1/alert-checkpoint")
        self.assertEqual(self.request("PUT", "/v1/alert-checkpoint", ALERT, etag)[0], 412)
        newer = dict(ALERT, sequence=2)
        self.assertEqual(self.request("PUT", "/v1/alert-checkpoint", newer, etag)[0], 204)
        self.assertEqual(self.request("PUT", "/v1/alert-checkpoint",
                                      dict(ALERT, sequence=3), etag)[0], 412)

    def test_concurrent_alert_create_single_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.request(
                "PUT", "/v1/alert-checkpoint", ALERT, "*")[0], range(2)))
        self.assertEqual(sorted(results), [204, 412])

    def test_client_rejects_wrong_namespace(self):
        with self.assertRaises(ValueError):
            HTTPSAlertCheckpointCustodian("https://example.com/v1/receipt", TOKEN)

    def test_client_validates_alert_schema(self):
        client = HTTPSAlertCheckpointCustodian(
            "https://example.com/v1/alert-checkpoint", TOKEN)
        client._observed = True
        client._last = None
        with self.assertRaises(ValueError):
            client.compare_and_swap(None, RECEIPT)


if __name__ == "__main__":
    unittest.main()
