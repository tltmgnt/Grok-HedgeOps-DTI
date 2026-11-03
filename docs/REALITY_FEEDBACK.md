# Phase 4 — Reality Feedback Ω

## Implemented

- Register quantitative predictions with a named metric, target, tolerance and unit.
- Record an observed value, source label, reviewer label and UTC timestamp.
- Compare measured value to target within an explicit absolute tolerance.
- Prevent duplicate evaluation of the same prediction.
- Produce an in-memory audit event sequence and state snapshot.

## Try offline

```bash
python feedback_demo.py
python -m unittest discover -s tests -v
```

The demo uses synthetic data, **not** an observed real-world result.

## Interpretation and limitations

`within_tolerance` means a single measurement lies within a specified interval;
it is **not** proof that an intervention caused an outcome. `outside_tolerance`
is not automatic falsification of the broader hypothesis. Source labels and reviewer
identities are user supplied and not authenticated. Audit events are in-memory and
can be modified by callers; they are not tamper-evident. No live data ingestion,
durable persistence, calibration or automated model learning is implemented.

## Next

Introduce durable append-only storage, source authentication, measurement windows,
baseline/control comparison, statistical decision rules, and a human-reviewed state
update protocol.
