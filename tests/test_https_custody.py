"""HTTP adapter tests without external network or credentials."""
import io
import json
import unittest
import urllib.error

from hedgeops.https_custody import HTTPSReceiptCustodian

URL = "https://custody.example.test/v1/receipt"
TOKEN = "test-only-custody-bearer-token"
FIRST = {"sequence": 1, "receipt_sha256": "a" * 64}
SECOND = {"sequence": 2, "receipt_sha256": "b" * 64}

class Response:
    def __init__(self, status, body=b"", etag='"v1"', url=URL):
        self.status = status
        self.headers = {"ETag": etag}
        self.body = io.BytesIO(body)
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, count=-1):
        return self.body.read(count)

    def geturl(self):
        return self.url

class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

def http_error(code):
    return urllib.error.HTTPError(URL, code, "test", {}, None)

class HTTPSCustodyTests(unittest.TestCase):
    def client(self, *responses):
        opener = FakeOpener(responses)
        return HTTPSReceiptCustodian(URL, TOKEN, opener=opener), opener

    def test_missing_then_create_conditional(self):
        client, opener = self.client(http_error(404), Response(201))
        self.assertIsNone(client.read())
        self.assertTrue(client.compare_and_swap(None, FIRST))
        self.assertEqual(opener.requests[1].get_header("If-none-match"), "*")
        self.assertEqual(json.loads(opener.requests[1].data), FIRST)

    def test_read_then_update_with_etag(self):
        client, opener = self.client(
            Response(200, json.dumps(FIRST).encode(), '"version-1"'),
            Response(204))
        self.assertEqual(client.read(), FIRST)
        self.assertTrue(client.compare_and_swap(FIRST, SECOND))
        self.assertEqual(opener.requests[1].get_header("If-match"), '"version-1"')
        self.assertEqual(opener.requests[0].get_header("Authorization"),
                         "Bearer " + TOKEN)

    def test_conflict_returns_false(self):
        client, _ = self.client(http_error(404), http_error(412))
        client.read()
        self.assertFalse(client.compare_and_swap(None, FIRST))

    def test_cas_without_read_rejected(self):
        client, opener = self.client()
        self.assertFalse(client.compare_and_swap(None, FIRST))
        self.assertFalse(opener.requests)

    def test_replayed_cas_rejected(self):
        client, opener = self.client(http_error(404), Response(201))
        client.read()
        self.assertTrue(client.compare_and_swap(None, FIRST))
        self.assertFalse(client.compare_and_swap(None, FIRST))
        self.assertEqual(len(opener.requests), 2)

    def test_missing_strong_etag_rejected(self):
        client, _ = self.client(Response(200, json.dumps(FIRST).encode(), 'W/"weak"'))
        with self.assertRaises(ValueError):
            client.read()

    def test_malformed_json_rejected(self):
        client, _ = self.client(Response(200, b"broken"))
        with self.assertRaises(ValueError):
            client.read()

    def test_redirected_read_rejected(self):
        client, _ = self.client(Response(200, json.dumps(FIRST).encode(),
                                         url="https://elsewhere.example.test/"))
        with self.assertRaises(ValueError):
            client.read()

    def test_non_https_url_rejected(self):
        with self.assertRaises(ValueError):
            HTTPSReceiptCustodian("http://custody.example.test/receipt", TOKEN)

    def test_short_token_rejected(self):
        with self.assertRaises(ValueError):
            HTTPSReceiptCustodian(URL, "short")

    def test_non_monotonic_update_rejected(self):
        client, opener = self.client(Response(200, json.dumps(FIRST).encode()))
        client.read()
        self.assertFalse(client.compare_and_swap(FIRST, FIRST))
        self.assertEqual(len(opener.requests), 1)

    def test_oversized_response_rejected(self):
        client, _ = self.client(Response(200, b"x" * 4097))
        with self.assertRaises(ValueError):
            client.read()

if __name__ == "__main__":
    unittest.main()
