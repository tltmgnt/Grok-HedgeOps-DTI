# Phase 5 — Persistent Intelligence Ω

The SQLite event store persists structured decision-support events across process
restarts. Each event contains a stream ID, type, JSON payload, timestamp and
SHA-256 hash linking it to the preceding global event.

## Run

```bash
python persistent_demo.py
python -m unittest discover -s tests -v
```

Use `HEDGEOPS_DB_PATH` to override the default `data/hedgeops.sqlite3`.

## API

`EventStore(path).append(stream, kind, payload)` appends a JSON event.
`history(stream)` retrieves one stream in insertion order.
`snapshot(stream)` returns the stream history plus global chain check.
`verify_chain()` checks for ordinary accidental modifications to stored records.

## Security and scope

- The database is local and not encrypted by this module.
- A privileged actor can rewrite both data and hashes; the hash chain is **not**
  independently anchored, signed or tamper-proof.
- Provenance is stored as supplied by callers; source authentication is not
  implemented.
- The store is not yet wired into the live Grok laboratory or FeedbackEngine.
- Replay currently returns the ordered event history, not a domain-specific
  materialized state reducer.
- No retention policy, migration framework, access control or backups exist.

Next: connect domain events to the lab and feedback engine, add replay reducers,
authenticated source capture and durable approval records.
