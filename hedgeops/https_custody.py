"""HTTPS custody adapter using HTTP conditional requests for atomic CAS.

The remote service must enforce durable monotonic state and conditional writes.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from hedgeops.store import canonical


class HTTPSReceiptCustodian:
    """Read and CAS a single independently hosted custody record.

    The server MUST support strong ETags, If-Match and If-None-Match: *.
    A bearer token authenticates the client; it does not make a server trusted.
    """

    def __init__(self, url, bearer_token, *, timeout=10, opener=None):
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or not parsed.netloc or
                parsed.username is not None or parsed.password is not None or
                parsed.fragment or not parsed.path):
            raise ValueError("Custody URL must be an absolute HTTPS resource")
        if not isinstance(bearer_token, str) or len(bearer_token) < 24 or any(
                ord(char) < 33 or ord(char) > 126 for char in bearer_token):
            raise ValueError("Invalid custody bearer token")
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError("Invalid custody timeout")
        self.url = url
        self._token = bearer_token
        self.timeout = timeout
        self._opener = opener or urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        self._last = None
        self._etag = None
        self._observed = False

    def _request(self, method, data=None, conditional=None):
        headers = {
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json",
            "Cache-Control": "no-store",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if conditional:
            headers.update(conditional)
        request = urllib.request.Request(
            self.url, data=data, headers=headers, method=method)
        return self._opener.open(request, timeout=self.timeout)

    def read(self):
        """Read the current record and its strong validator; never use cache."""
        self._observed = False
        self._last = None
        self._etag = None
        try:
            response = self._request("GET")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                self._observed = True
                return None
            raise
        with response:
            if response.geturl() != self.url:
                raise ValueError("Redirected custody reads are forbidden")
            if response.status != 200:
                raise ValueError("Unexpected custody read status")
            etag = response.headers.get("ETag")
            if (not isinstance(etag, str) or not etag.startswith('"') or
                    not etag.endswith('"') or len(etag) < 3 or
                    any(char in etag for char in "\r\n")):
                raise ValueError("Strong custody ETag required")
            raw = response.read(4097)
            if len(raw) > 4096:
                raise ValueError("Custody response too large")
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid custody JSON") from exc
        if not isinstance(record, dict):
            raise ValueError("Custody response must be an object")
        self._observed = True
        self._last = record
        self._etag = etag
        return dict(record)

    def compare_and_swap(self, expected, new):
        """Perform a conditional PUT based on the immediately prior read."""
        if not self._observed or expected != self._last:
            return False
        from hedgeops.receipt_custody import _validate
        _validate(new)
        if expected is not None:
            _validate(expected)
            if (new["sequence"] <= expected["sequence"] or
                    not self._etag):
                return False
        else:
            if new["sequence"] != 1:
                return False
        conditional = ({"If-Match": self._etag} if expected is not None
                       else {"If-None-Match": "*"})
        data = canonical(new).encode("utf-8")
        try:
            response = self._request("PUT", data=data, conditional=conditional)
        except urllib.error.HTTPError as exc:
            self._observed = False
            if exc.code in (409, 412, 428):
                return False
            raise
        self._observed = False
        with response:
            if response.geturl() != self.url:
                raise ValueError("Redirected custody writes are forbidden")
            if response.status not in (200, 201, 204):
                raise ValueError("Unexpected custody write status")
        return True
