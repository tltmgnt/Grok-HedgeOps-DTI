"""Reference SQLite-backed receipt custodian HTTP server.

Run behind a TLS-terminating reverse proxy; never expose plain HTTP publicly.
SQLite state and its backups require independent, rollback-resistant custody.
"""
import hashlib
import hmac
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hedgeops.admission import AdmissionController
from hedgeops.connection_server import BoundedCustodyHTTPServer
from hedgeops.custody_metrics import CustodyMetrics
from hedgeops.custody_alert_anchor import _record as _validate_alert
from hedgeops.receipt_custody import _validate
from hedgeops.store import canonical

MAX_BODY = 4096
REQUEST_TIMEOUT_SECONDS = 5


def _etag(record):
    return '"' + hashlib.sha256(canonical(record).encode("utf-8")).hexdigest() + '"'


class CustodyDatabase:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS custody (id INTEGER PRIMARY KEY CHECK (id=1), sequence INTEGER NOT NULL, digest TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS alert_custody (id INTEGER PRIMARY KEY CHECK (id=1), sequence INTEGER NOT NULL, digest TEXT NOT NULL)")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def healthy(self):
        """Check the database can be read and passes SQLite quick_check."""
        with self._connect() as db:
            return db.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    def read(self):
        with self._connect() as db:
            row = db.execute("SELECT sequence,digest FROM custody WHERE id=1").fetchone()
            return None if row is None else {"sequence": row[0], "receipt_sha256": row[1]}

    def cas(self, condition, record):
        _validate(record)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT sequence,digest FROM custody WHERE id=1").fetchone()
            current = None if row is None else {"sequence": row[0], "receipt_sha256": row[1]}
            if current is None:
                if condition != "*" or record["sequence"] != 1:
                    return False
                db.execute("INSERT INTO custody(id,sequence,digest) VALUES(1,?,?)",
                           (record["sequence"], record["receipt_sha256"]))
            else:
                if (condition != _etag(current) or
                        record["sequence"] <= current["sequence"]):
                    return False
                db.execute("UPDATE custody SET sequence=?,digest=? WHERE id=1",
                           (record["sequence"], record["receipt_sha256"]))
            db.commit()
            return True


    def read_alert(self):
        with self._connect() as db:
            row = db.execute("SELECT sequence,digest FROM alert_custody WHERE id=1").fetchone()
            return None if row is None else {"sequence": row[0], "checkpoint_sha256": row[1]}

    def cas_alert(self, condition, record):
        _validate_alert(record)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT sequence,digest FROM alert_custody WHERE id=1").fetchone()
            current = None if row is None else {"sequence": row[0], "checkpoint_sha256": row[1]}
            if current is None:
                if condition != "*" or record["sequence"] != 1:
                    return False
                db.execute("INSERT INTO alert_custody(id,sequence,digest) VALUES(1,?,?)",
                           (record["sequence"], record["checkpoint_sha256"]))
            else:
                if condition != _etag(current) or record["sequence"] <= current["sequence"]:
                    return False
                db.execute("UPDATE alert_custody SET sequence=?,digest=? WHERE id=1",
                           (record["sequence"], record["checkpoint_sha256"]))
            db.commit()
            return True


def make_handler(database, bearer_token, *, admission=None, metrics=None):
    """Create a handler bound to a database and an operator-managed secret."""
    if not isinstance(bearer_token, str) or len(bearer_token) < 24:
        raise ValueError("Bearer token must be at least 24 characters")
    token_bytes = bearer_token.encode("utf-8")
    admission = admission if admission is not None else AdmissionController()
    metrics = metrics if metrics is not None else CustodyMetrics()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

        def log_message(self, format, *args):
            # Avoid logging headers, credentials, or request bodies.
            pass

        def _reply(self, status, payload=b"", etag=None):
            method = self.command if self.command in ("GET", "PUT") else "GET"
            route = ("receipt" if self.path == "/v1/receipt" else
                     "health" if self.path == "/v1/health" else "other")
            metrics.record(method, route, status)
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "application/json")
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()
            if payload:
                self.wfile.write(payload)

        def _authorized(self):
            if len(self.headers.get_all("Authorization", [])) != 1:
                self._reply(401)
                return False
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(
                    supplied.encode("utf-8"), b"Bearer " + token_bytes):
                self._reply(401)
                return False
            return True

        def _valid_framing(self, *, body=False):
            if self.headers.get_all("Transfer-Encoding", []):
                self.close_connection = True
                self._reply(400)
                return False
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1 or (not body and lengths):
                self.close_connection = True
                self._reply(400)
                return False
            if body and len(lengths) != 1:
                self.close_connection = True
                self._reply(411)
                return False
            return True

        def do_GET(self):
            if not self._valid_framing():
                return
            if self.path not in ("/v1/receipt", "/v1/alert-checkpoint", "/v1/health"):
                self._reply(404)
                return
            if not self._authorized():
                return
            try:
                if self.path == "/v1/health":
                    self._reply(200 if database.healthy() else 503)
                    return
                record = (database.read_alert() if self.path == "/v1/alert-checkpoint"
                          else database.read())
                if record is None:
                    self._reply(404)
                else:
                    self._reply(200, canonical(record).encode("utf-8"), _etag(record))
            except sqlite3.Error:
                self.close_connection = True
                self._reply(503)

        def do_PUT(self):
            if not self._valid_framing(body=True):
                return
            if (len(self.headers.get_all("If-Match", [])) > 1 or
                    len(self.headers.get_all("If-None-Match", [])) > 1):
                self.close_connection = True
                self._reply(400)
                return
            if self.path not in ("/v1/receipt", "/v1/alert-checkpoint"):
                self._reply(404)
                return
            if not self._authorized():
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                self._reply(400)
                return
            if length < 1 or length > MAX_BODY:
                self.close_connection = True
                self._reply(413)
                return
            raw = self.rfile.read(length)
            try:
                record = json.loads(raw.decode("utf-8"))
                (_validate_alert if self.path == "/v1/alert-checkpoint" else _validate)(record)
            except (ValueError, UnicodeError, TypeError):
                self._reply(400)
                return
            if_match = self.headers.get("If-Match")
            if_none = self.headers.get("If-None-Match")
            if (bool(if_match) == bool(if_none) or
                    (if_none is not None and if_none != "*") or
                    (if_match is not None and (not if_match.startswith('"') or
                     not if_match.endswith('"') or "," in if_match))):
                self._reply(428)
                return
            condition = if_match if if_match is not None else "*"
            try:
                accepted = (database.cas_alert(condition, record)
                            if self.path == "/v1/alert-checkpoint"
                            else database.cas(condition, record))
                if accepted:
                    self._reply(204)
                else:
                    self._reply(412)
            except sqlite3.Error:
                self.close_connection = True
                self._reply(503)

    # Guard requests before database access; close rejected connections to
    # prevent unread request bodies from being interpreted as new requests.
    for method in ("do_GET", "do_PUT"):
        original = getattr(Handler, method)

        def guarded(self, _original=original):
            result = admission.enter(self.client_address[0])
            if result != "ok":
                self.close_connection = True
                self._reply(429 if result == "rate" else 503)
                return
            try:
                return _original(self)
            finally:
                admission.leave()

        setattr(Handler, method, guarded)
    return Handler


def serve(database_path, bearer_token, *, host="127.0.0.1", port=8765,
          max_connections=32):
    """Blocking local-only reference server; TLS must be provided upstream."""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("Reference server only binds to loopback")
    database = CustodyDatabase(database_path)
    server = BoundedCustodyHTTPServer(
        (host, port), make_handler(database, bearer_token),
        max_connections=max_connections)
    try:
        server.serve_forever()
    finally:
        server.server_close()
