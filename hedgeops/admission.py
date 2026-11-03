"""Thread-safe admission limits for the loopback custody reference server."""
import threading
import time
from collections import deque


class AdmissionController:
    def __init__(self, *, requests_per_window=60, window_seconds=60,
                 max_inflight=8, clock=None):
        if (type(requests_per_window) is not int or requests_per_window < 1 or
                type(max_inflight) is not int or max_inflight < 1 or
                not isinstance(window_seconds, (int, float)) or
                window_seconds <= 0):
            raise ValueError("Invalid admission limits")
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.clock = clock or time.monotonic
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(max_inflight)
        self.requests = {}

    def enter(self, client):
        if not self.slots.acquire(blocking=False):
            return "busy"
        now = self.clock()
        with self.lock:
            for peer in list(self.requests):
                times = self.requests[peer]
                while times and now - times[0] >= self.window_seconds:
                    times.popleft()
                if not times:
                    del self.requests[peer]
            times = self.requests.setdefault(client, deque())
            if len(times) >= self.requests_per_window:
                self.slots.release()
                return "rate"
            times.append(now)
        return "ok"

    def leave(self):
        self.slots.release()
