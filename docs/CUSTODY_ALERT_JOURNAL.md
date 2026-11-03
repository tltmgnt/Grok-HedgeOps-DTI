# Phase 38 — Durable custody alert journal

`CustodyAlertJournal` stores Phase 37 alert-monitor evaluations in a
SQLite-backed, SHA-256 hash-chained sequence. Each append runs inside
`BEGIN IMMEDIATE` and verifies the existing chain before extending it.

```python
from hedgeops.custody_alert_journal import CustodyAlertJournal

journal = CustodyAlertJournal("/protected/custody-alerts.sqlite3")
journal.append(monitor.sample(metrics, server))
assert journal.verify()
head = journal.head()  # sequence and event_hash
```

Journal entries contain only `baseline`, `counter_reset`, and allowlisted
alert event/count/threshold fields. They never include bearer tokens,
request bodies, arbitrary URLs, IP addresses or receipt contents.

**Important limitations:** Journal writes are caller-driven; there is no
automatic sampling or notification. A local SHA-256 chain detects edits,
missing intermediate records and invalid payloads but cannot detect
deletion of a suffix, replacement of the entire database or a valid
recomputed chain without an independently retained trusted head.
Persist `head()` separately in independently protected custody before
relying on it as a rollback checkpoint. This module does not provide an
external anchor, signature, immutable storage or trusted timestamp.

Run `python release_check.py --verbose` and confirm both CI jobs.
