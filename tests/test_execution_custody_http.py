"""Phase 55: real HTTP execution checkpoint custody protocol tests."""
import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase, make_handler
from hedgeops.https_custody import HTTPSExecutionCheckpointCustodian

TOKEN = "phase55-execution-test-token-long"
PATH = "/v1/execution-checkpoint"
URL = "https://custody.example.test" + PATH
FIRST = {"sequence": 1, "checkpoint_sha256": "a" * 64}
SECOND = {"sequence": 2, "checkpoint_sha256": "b" * 64}


class LocalResponse:
    def __init__(self, response, connection):
        self.response = response
        self.connection = connection
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


class LocalOpener:
    """Route HTTPS-shaped requests to an ephemeral local HTTP server."""
    def __init__(self, port):
        self.port = port

    def open(self, request, timeout):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = dict(request.header_items())
        method = request.get_method()
        if method == "GET":
            connection.putrequest("GET", PATH)
            for name, value in headers.items():
                if name.lower() not in ("content-length", "transfer-encoding"):
                    connection.putheader(name, value)
            connection.endheaders()
        else:
            connection.request(method, PATH, body=request.data, headers=headers)
        response = connection.getresponse()
        if response.status >= 400:
            status = response.status
            response.read()
            connection.close()
            raise urllib.error.HTTPError(URL, status, "local test", {}, None)
        return LocalResponse(response, connection)


class ExecutionHTTPTests(unittest.TestCase):
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

    def request(self, method, record=None, condition=None, token=TOKEN,
                path=PATH, extra=None):
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        headers = {"Authorization": "Bearer " + token}
        if condition is not None:
            headers["If-None-Match" if condition == "*" else "If-Match"] = condition
        if extra:
            headers.update(extra)
        body = json.dumps(record).encode() if record is not None else None
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        status, etag, data = response.status, response.getheader("ETag"), response.read()
        conn.close()
        return status, etag, json.loads(data) if data else None

    def test_round_trip(self):
        self.assertEqual(self.request("GET")[0], 404)
        self.assertEqual(self.request("PUT", FIRST, "*")[0], 204)
        status, etag, record = self.request("GET")
        self.assertEqual(status, 200)
        self.assertEqual(record, FIRST)
        self.assertTrue(etag.startswith('"') and etag.endswith('"'))
        self.assertEqual(self.request("PUT", SECOND, etag)[0], 204)
        self.assertEqual(self.request("GET")[2], SECOND)

    def test_authentication_denied(self):
        self.assertEqual(self.request("GET", token="invalid")[0], 401)
        self.assertEqual(self.request("PUT", FIRST, "*", token="invalid")[0], 401)
        self.assertIsNone(self.db.read_execution())

    def test_replay_and_stale_etag(self):
        self.request("PUT", FIRST, "*")
        etag = self.request("GET")[1]
        self.assertEqual(self.request("PUT", FIRST, etag)[0], 412)
        self.assertEqual(self.request("PUT", SECOND, '"stale"')[0], 412)
        self.assertEqual(self.db.read_execution(), FIRST)

    def test_missing_condition(self):
        self.assertEqual(self.request("PUT", FIRST)[0], 428)
        self.assertIsNone(self.db.read_execution())

    def test_invalid_schema(self):
        bad = {"sequence": True, "checkpoint_sha256": "a" * 64}
        self.assertEqual(self.request("PUT", bad, "*")[0], 400)
        self.assertIsNone(self.db.read_execution())

    def test_namespace_isolation(self):
        self.request("PUT", FIRST, "*")
        self.assertEqual(self.request("GET", path="/v1/receipt")[0], 404)
        self.assertEqual(self.request("GET", path="/v1/alert-checkpoint")[0], 404)
        self.assertEqual(self.request("GET", path="/v1/fence-audit")[0], 404)

    def test_concurrent_create_single_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(
                lambda _: self.request("PUT", FIRST, "*")[0], range(2)))
        self.assertEqual(sorted(statuses), [204, 412])

    def test_https_adapter_round_trip(self):
        client = HTTPSExecutionCheckpointCustodian(
            URL, TOKEN, opener=LocalOpener(self.server.server_port))
        self.assertIsNone(client.read())
        self.assertTrue(client.compare_and_swap(None, FIRST))
        self.assertEqual(client.read(), FIRST)
        self.assertTrue(client.compare_and_swap(FIRST, SECOND))
        self.assertEqual(client.read(), SECOND)

    def test_https_adapter_rejects_replay(self):
        client = HTTPSExecutionCheckpointCustodian(
            URL, TOKEN, opener=LocalOpener(self.server.server_port))
        self.assertIsNone(client.read())
        self.assertTrue(client.compare_and_swap(None, FIRST))
        self.assertEqual(client.read(), FIRST)
        self.assertFalse(client.compare_and_swap(FIRST, FIRST))

    def test_wrong_namespace_payload(self):
        wrong = {"sequence": 1, "receipt_sha256": "a" * 64}
        self.assertEqual(self.request("PUT", wrong, "*")[0], 400)


if __name__ == "__main__":
    unittest.main()
