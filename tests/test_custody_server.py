"""Reference custody server persistence, authorization and CAS tests."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from hedgeops.custody_server import CustodyDatabase, make_handler

TOKEN = "test-only-custody-server-token"
FIRST = {"sequence": 1, "receipt_sha256": "a" * 64}
SECOND = {"sequence": 2, "receipt_sha256": "b" * 64}

class CustodyServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "custody.sqlite3"
        self.database = CustodyDatabase(self.path)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(self.database, TOKEN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, method, body=None, token=TOKEN, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        fields = {"Authorization": "Bearer " + token}
        fields.update(headers or {})
        data = None if body is None else json.dumps(body).encode("utf-8")
        conn.request(method, "/v1/receipt", body=data, headers=fields)
        response = conn.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        conn.close()
        return result

    def test_initial_get_missing(self):
        self.assertEqual(self.request("GET")[0], 404)

    def test_create_read_update_and_persist(self):
        self.assertEqual(self.request("PUT", FIRST, headers={"If-None-Match": "*"})[0], 204)
        status, headers, raw = self.request("GET")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), FIRST)
        self.assertTrue(headers["ETag"].startswith('"'))
        self.assertEqual(self.request("PUT", SECOND, headers={"If-Match": headers["ETag"]})[0], 204)
        self.assertEqual(CustodyDatabase(self.path).read(), SECOND)

    def test_stale_etag_rejected(self):
        self.request("PUT", FIRST, headers={"If-None-Match": "*"})
        self.assertEqual(self.request("PUT", SECOND, headers={"If-Match": '"old"'})[0], 412)
        self.assertEqual(self.database.read(), FIRST)

    def test_non_monotonic_rejected(self):
        self.request("PUT", FIRST, headers={"If-None-Match": "*"})
        etag = self.request("GET")[1]["ETag"]
        self.assertEqual(self.request("PUT", FIRST, headers={"If-Match": etag})[0], 412)

    def test_unauthorized_rejected(self):
        self.assertEqual(self.request("GET", token="wrong")[0], 401)
        self.assertEqual(self.request("PUT", FIRST, token="wrong",
                                      headers={"If-None-Match": "*"})[0], 401)

    def test_missing_condition_rejected(self):
        self.assertEqual(self.request("PUT", FIRST)[0], 428)

    def test_invalid_record_rejected(self):
        self.assertEqual(self.request("PUT", {"sequence": True, "receipt_sha256": "a" * 64},
                                      headers={"If-None-Match": "*"})[0], 400)

    def test_competing_writers_one_wins(self):
        outcomes = []
        barrier = threading.Barrier(2)
        def attempt(record):
            barrier.wait(timeout=3)
            outcomes.append(self.request("PUT", record, headers={"If-None-Match": "*"})[0])
        t1 = threading.Thread(target=attempt, args=(FIRST,))
        t2 = threading.Thread(target=attempt, args=({"sequence": 1, "receipt_sha256": "c" * 64},))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(sorted(outcomes), [204, 412])

    def test_database_rejects_wrong_first_sequence(self):
        self.assertFalse(self.database.cas("*", SECOND))

    def test_database_rejects_repeated_create(self):
        self.assertTrue(self.database.cas("*", FIRST))
        self.assertFalse(self.database.cas("*", FIRST))

if __name__ == "__main__":
    unittest.main()
