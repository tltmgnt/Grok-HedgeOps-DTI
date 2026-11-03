"""Deterministic, secret-free custody alert evaluation over counter deltas."""

EVENTS = ("authentication_failures", "rate_limited", "service_unavailable",
          "connection_rejections")


class AlertThresholds:
    """Nonnegative integer thresholds for an observation interval."""

    def __init__(self, *, authentication_failures=5, rate_limited=10,
                 service_unavailable=1, connection_rejections=1):
        values = dict(authentication_failures=authentication_failures,
                      rate_limited=rate_limited,
                      service_unavailable=service_unavailable,
                      connection_rejections=connection_rejections)
        if any(type(value) is not int or value < 1 for value in values.values()):
            raise ValueError("Alert thresholds must be positive integers")
        self.values = values


def _snapshot(metrics, server):
    counts = dict.fromkeys(EVENTS, 0)
    for row in metrics.snapshot():
        status = row["status"]
        value = row["count"]
        if type(value) is not int or value < 0:
            raise ValueError("Invalid metrics counter")
        if status == 401:
            counts["authentication_failures"] += value
        elif status == 429:
            counts["rate_limited"] += value
        elif status == 503:
            counts["service_unavailable"] += value
    rejected = server.rejected_connections
    if type(rejected) is not int or rejected < 0:
        raise ValueError("Invalid connection counter")
    counts["connection_rejections"] = rejected
    return counts


class CustodyAlertMonitor:
    """Evaluate per-interval deltas; no network, clock or notification side effects.

    Call sample() once to establish a baseline, then again after each interval.
    Counter resets fail closed: no alerts are emitted from ambiguous deltas and
    a fresh baseline is established. Monitor state is process-local.
    """

    def __init__(self, thresholds=None):
        self.thresholds = thresholds if thresholds is not None else AlertThresholds()
        if not isinstance(self.thresholds, AlertThresholds):
            raise TypeError("Invalid alert thresholds")
        self._previous = None

    def sample(self, metrics, server):
        current = _snapshot(metrics, server)
        if self._previous is None:
            self._previous = current
            return {"baseline": True, "counter_reset": False, "alerts": []}
        previous = self._previous
        self._previous = current
        if any(current[name] < previous[name] for name in EVENTS):
            return {"baseline": True, "counter_reset": True, "alerts": []}
        alerts = []
        for name in EVENTS:
            delta = current[name] - previous[name]
            threshold = self.thresholds.values[name]
            if delta >= threshold:
                alerts.append({"event": name, "count": delta,
                               "threshold": threshold})
        return {"baseline": False, "counter_reset": False, "alerts": alerts}
