"""Reference SQLite-backed receipt custodian HTTP server.

Run behind a TLS-terminating reverse proxy; never expose plain HTTP publicly.
SQLite state and its backups require independent, rollback-resistant custody.
"""
import hashlib
import hmac
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hedgeops.receipt_custody import _validate
from hedgeops.store import canonical

MAX_BODY = 4096


def _etag(record):
    return '"' + hashlib.sha256(canonical(record).encode("utf-8")).hexdigest() + '"'


class CustodyDatabase:
    def __init__(self, path):
        self.path = str(path)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS custody (id INTEGER PRIMARY KEY CHECK (id=1), sequence INTEGER NOT NULL, digest TEXT NOT NULL)")
            db.commit()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        return db

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


def make_handler(database, bearer_token):
    """Create a handler bound to a database and an operator-managed secret."""
    if not isinstance(bearer_token, str) or len(bearer_token) < 24:
        raise ValueError("Bearer token must be at least 24 characters")
    token_bytes = bearer_token.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            # Avoid logging headers, credentials, or request bodies.
            pass

        def _reply(self, status, payload=b"", etag=None):
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
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(
                    supplied.encode("utf-8"), b"Bearer " + token_bytes):
                self._reply(401)
                return False
            return True

        def do_GET(self):
            if self.path != "/v1/receipt":
                self._reply(404)
                return
            if not self._authorized():
                return
            record = database.read()
            if record is None:
                self._reply(404)
            else:
                self._reply(200, canonical(record).encode("utf-8"), _etag(record))

        def do_PUT(self):
            if self.path != "/v1/receipt":
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
                self._reply(413)
                return
            raw = self.rfile.read(length)
            try:
                record = json.loads(raw.decode("utf-8"))
                _validate(record)
            except (ValueError, UnicodeError, TypeError):
                self._reply(400)
                return
            if_match = self.headers.get("If-Match")
            if_none = self.headers.get("If-None-Match")
            if (bool(if_match) == bool(if_none) or
                    (if_none is not None and if_none != "*")):
                self._reply(428)
                return
            condition = if_match if if_match is not None else "*"
            if database.cas(condition, record):
                self._reply(204)
            else:
                self._reply(412)

    return Handler


def serve(database_path, bearer_token, *, host="127.0.0.1", port=8765):
    """Blocking local-only reference server; TLS must be provided upstream."""
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("Reference server only binds to loopback")
    database = CustodyDatabase(database_path)
    server = ThreadingHTTPServer((host, port), make_handler(database, bearer_token))
    try:
        server.serve_forever()
    finally:
        server.server_close()
