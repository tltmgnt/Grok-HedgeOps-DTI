"""Phase 32: real HTTP client/server protocol and request hardening."""
import http.client
import json
import tempfile
import threading
import urllib.error
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase, make_handler
from hedgeops.https_custody import HTTPSReceiptCustodian

TOKEN = "phase32-test-only-bearer-token"
URL = "https://custody.example.test/v1/receipt"
FIRST = {"sequence": 1, "receipt_sha256": "a" * 64}
SECOND = {"sequence": 2, "receipt_sha256": "b" * 64}


class LocalOpener:
    """Route HTTPS-shaped client requests to the local HTTP test server."""
    def __init__(self, port):
        self.port = port

    def open(self, request, timeout):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = dict(request.header_items())
        method = request.get_method()
        # http.client may add Content-Length: 0 to bodyless methods.
        # Emit an explicit bodyless GET without framing headers.
        if method == "GET":
            headers = {key: value for key, value in headers.items()
                       if key.lower() not in ("content-length", "transfer-encoding")}
            connection.putrequest("GET", "/v1/receipt")
            for key, value in headers.items():
                connection.putheader(key, value)
            connection.endheaders()
        else:
            connection.request(method, "/v1/receipt",
                               body=request.data, headers=headers)
        response = connection.getresponse()
        if response.status >= 400:
            code = response.status
            response.read()
            connection.close()
            raise urllib.error.HTTPError(URL, code, 'local test', {}, None)
        return LocalResponse(response, connection)


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


class Phase32Tests(unittest.TestCase):
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

    def request(self, method, headers, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request(method, "/v1/receipt", body=body, headers=headers)
        response = conn.getresponse()
        status = response.status
        response.read()
        conn.close()
        return status

    def test_client_server_round_trip(self):
        client = HTTPSReceiptCustodian(
            URL, TOKEN, opener=LocalOpener(self.server.server_port))
        self.assertIsNone(client.read())
        self.assertTrue(client.compare_and_swap(None, FIRST))
        self.assertEqual(client.read(), FIRST)
        self.assertTrue(client.compare_and_swap(FIRST, SECOND))
        self.assertEqual(client.read(), SECOND)

    def test_duplicate_authorization_rejected(self):
        headers = {"Authorization": "Bearer " + TOKEN}
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.putrequest("GET", "/v1/receipt")
        conn.putheader("Authorization", "Bearer " + TOKEN)
        conn.putheader("Authorization", "Bearer " + TOKEN)
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        response.read()
        conn.close()

    def test_transfer_encoding_rejected(self):
        self.assertEqual(self.request("PUT", {
            "Authorization": "Bearer " + TOKEN,
            "Transfer-Encoding": "chunked",
            "If-None-Match": "*",
        }), 400)

    def test_missing_length_rejected(self):
        # HTTPConnection.request automatically supplies Content-Length: 0
        # for PUT, so use the low-level API to truly omit the header.
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        conn.putrequest("PUT", "/v1/receipt")
        conn.putheader("Authorization", "Bearer " + TOKEN)
        conn.putheader("If-None-Match", "*")
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 411)
        response.read()
        conn.close()

    def test_invalid_etag_condition_rejected(self):
        self.assertEqual(self.request("PUT", {
            "Authorization": "Bearer " + TOKEN,
            "If-Match": 'W/"weak"',
            "Content-Type": "application/json",
        }, json.dumps(FIRST).encode()), 428)

    def test_rejected_request_does_not_mutate(self):
        self.test_transfer_encoding_rejected()
        self.assertIsNone(self.db.read())


if __name__ == "__main__":
    unittest.main()
