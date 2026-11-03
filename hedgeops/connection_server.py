"""Bounded thread creation for the loopback reference custody HTTP server."""
import threading
from http.server import ThreadingHTTPServer


class BoundedCustodyHTTPServer(ThreadingHTTPServer):
    """Refuse excess accepted sockets before starting a handler thread.

    Rejected sockets receive no HTTP response; this prevents creation of
    unbounded threads. An upstream proxy must handle connection-level errors.
    """

    def __init__(self, server_address, handler_class, *, max_connections=32):
        if type(max_connections) is not int or max_connections < 1:
            raise ValueError("max_connections must be a positive integer")
        self._connection_slots = threading.BoundedSemaphore(max_connections)
        self._connection_lock = threading.Lock()
        self._active_connections = 0
        self._rejected_connections = 0
        super().__init__(server_address, handler_class)

    @property
    def active_connections(self):
        with self._connection_lock:
            return self._active_connections

    @property
    def rejected_connections(self):
        with self._connection_lock:
            return self._rejected_connections

    def process_request(self, request, client_address):
        if not self._connection_slots.acquire(blocking=False):
            with self._connection_lock:
                self._rejected_connections += 1
            self.shutdown_request(request)
            return
        with self._connection_lock:
            self._active_connections += 1
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._release_slot()
            raise

    def _release_slot(self):
        with self._connection_lock:
            self._active_connections -= 1
        self._connection_slots.release()

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._release_slot()
