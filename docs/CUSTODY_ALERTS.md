# Phase 37 — Custody alert thresholds

`hedgeops.custody_alerts` evaluates deterministic per-interval security
alerts from the Phase 36 `CustodyMetrics` counters and the Phase 35
connection-rejection counter.

```python
from hedgeops.custody_alerts import CustodyAlertMonitor, AlertThresholds

monitor = CustodyAlertMonitor(AlertThresholds(
    authentication_failures=5,
    rate_limited=10,
    service_unavailable=1,
    connection_rejections=1))
monitor.sample(metrics, server)  # establish baseline
result = monitor.sample(metrics, server)  # evaluate next interval
```

The caller controls sampling cadence and any alert delivery. Thresholds
count **new events since the previous sample**, not lifetime totals.
A first sample establishes a baseline. If any counter decreases (such as
after a process restart), the monitor marks `counter_reset=True` and
establishes a new baseline rather than fabricating deltas.

Alerts contain only fixed event names, integer counts and thresholds;
they never include credentials, request contents, receipt fingerprints,
client IP addresses or arbitrary URLs.

This is an in-memory evaluator, **not** a scheduler, durable incident
journal or notification service. It does not prove that counters were not
tampered with, and a restart can lose events. Operators must provide
external monitoring, secure alert delivery and independent custody
infrastructure before production use.

Run `python release_check.py --verbose` and verify both CI matrix jobs.
