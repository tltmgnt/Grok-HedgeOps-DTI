# Phase 9 — Reliability and Security Ω (incremental)

## Atomic case transitions

The SQLite event store now supports `expected_stream_events` on `append`.
It checks the stream event count **inside** a `BEGIN IMMEDIATE` transaction,
then appends or rejects a stale write. Case review, prediction proposal,
measurement recording and recovery use this optimistic concurrency check.

This reduces duplicate transitions from concurrent writers but does not prevent
all races involving external systems. Do not treat the journal as a distributed
transaction coordinator.

## API attempt budget

The live Grok adapter now accepts `max_requests` (default 10), counting each
attempt including retries. A five-agent run can consume up to 10 attempts
with one retry per agent. This is an **attempt budget**, not a monetary
or token budget, and it is in-memory and single-process only.

## Test

```bash
python -m unittest discover -s tests -v
```

## Outstanding security work

- Shared-secret operator access is not authenticated user identity.
- Lower-level review functions remain unprotected unless behind an enforced
  authorization boundary.
- API cost ceilings, usage telemetry and distributed quotas are not implemented.
- Database encryption, backups, signed external audit anchors and key rotation
  are not implemented.
- Provider integration and current CI results must be validated before merge.
