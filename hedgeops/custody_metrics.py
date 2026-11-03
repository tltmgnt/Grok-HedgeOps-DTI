"""Bounded-cardinality, secret-free custody security counters."""
import threading

_STATUSES = frozenset((200, 201, 204, 400, 401, 404, 411, 412, 413, 428, 429, 503))
_METHODS = frozenset(("GET", "PUT"))
_ROUTES = frozenset(("receipt", "health", "other"))


class CustodyMetrics:
    """Thread-safe counters. Never store credentials, URLs or request bodies."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counts = {}

    def record(self, method, route, status):
        if method not in _METHODS or route not in _ROUTES or status not in _STATUSES:
            raise ValueError("Unsupported metric dimensions")
        key = (method, route, status)
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self):
        with self._lock:
            return [
                {"method": method, "route": route, "status": status, "count": count}
                for (method, route, status), count in sorted(self._counts.items())
            ]
