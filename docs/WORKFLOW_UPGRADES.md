# Multi-horizon operational upgrade contract

Status: local session indexing implemented; production acceptance remains open.
This document defines completion criteria, not a 10/10 certification.

## Implemented foundation

`workflow_ledger.py` uses standard-library SQLite with full synchronous commits,
unique immutable run IDs, idempotent imports, conflict rejection and UTC timestamps.
The optional persistent worker indexes every returned session before continuing,
including failed sessions, and stops if indexing fails. It still stops on session
errors. There is no automatic restart or change to order limits.

Reports support 1 second, 10/20/30/40/50/60 minutes, daily, monthly and quarterly.
Minute/second windows are rolling inclusive windows. Calendar windows begin at
00:00 UTC and represent the current partial period. These reports count observed
session statuses and strategy versions and show observation age. They do not
measure tick coverage, missed runs, fills or investment performance.

```sh
python workflow_ledger.py --horizon 10m
python workflow_ledger.py --horizon quarterly
python workflow_ledger.py --session path/to/session.json --run-id unique-run-id
python paper_research_worker.py --monitor-only --ledger data/workflow-ledger.sqlite3
```

Keep the database and session files on a private persistent volume. Back up using
SQLite's backup API; validate restores. A local database does not coordinate
separate hosts or persist between GitHub-hosted runners. Actions sessions must be
explicitly imported into the same durable system before claiming aggregate coverage.
Never upload holdings, credentials or this database as public artifacts.

## Required upgrades and acceptance evidence

| Horizon | Upgrade still required | Evidence required to close |
|---|---|---|
| 1 second | Streaming event collector, sequence checks, durable offsets, disconnect detection; isolate AI from event loop | Replay duplicates, gaps, out-of-order events and disconnects; measure source-to-ledger latency against a declared SLO |
| 10 minutes | Expected-run manifest, heartbeat and operational reconciliation | Inject a missed run and stale feed; detect both within the declared deadline |
| 20 minutes | Persistent exception lifecycle and owner assignment | Unresolved broker state remains linked to one incident across runs |
| 30 minutes | Shared market/account snapshot and consistent research/risk state | All decisions identify snapshot, policy and order IDs; stale snapshots block entries |
| 40 minutes | Incident aging and fail-closed execution gate | Unknown order state blocks entries while reconciliation and observation continue |
| 50 minutes | Evidence completeness and alert acknowledgment check | Missing evidence and unacknowledged alerts appear in the hourly rollup |
| 60 minutes | Separate operational rollup from offline synthetic checks | Report expected/actual runs, failures, backlog and source age without treating CI success as broker health |
| Daily | Market-calendar-aware close job, canonical fill ledger and cash-flow accounting | Broker totals reconcile; partial fills and ambiguous orders are explicit; failed and skipped sessions retained |
| Monthly | Strategy-specific attribution, costs, benchmark and drift analysis | Version-separated returns with sample counts, missingness and uncertainty; no account-wide alpha claims |
| Quarterly | Governance, restore/recovery drill, access review and versioned policy decision | Reviewed evidence, verified restore, incident closure and recorded approve/reject decision |

## Cross-cutting release gates

1. Enforce one execution owner across Actions, manual order paths and external workers.
   A distributed lease alone is insufficient: expiry during a broker request can
   leave two owners. Use a single execution gateway with enforceable fencing and
   deterministic broker IDs; test network partitions, owner death and ambiguous POSTs.
2. Provide an independently monitored runtime and heartbeat. Reconciliation must
   precede execution restart. Never blindly retry an uncertain order submission.
3. Declare latency/availability objectives and evaluate them over an agreed period.
   A scheduler interval is not an uptime or response-time guarantee.
4. Persist canonical events, intents, acknowledgments, fills and versions with
   migrations, backups, access control, retention and tested recovery.
5. Keep observer alerts distinct from experiment exits: 5%/10% monitoring alerts
   do not replace the strategy's 3% loss-exit hypothesis or guarantee stop prices.
6. Preserve bounded paper-only execution until a separately reviewed release.
   Operational completeness does not establish profitable trading performance.

## Deployment sequence

First deploy the ledger in monitor-only mode with a persistent private volume.
Then unify ownership and reconciliation, deploy independently supervised event
collection, add expected-run tracking and incident aging, and finally add calendar
rollups and governance. Do not run multiple order-capable workers to obtain faster
cadences. The 20/40/50-minute stages are exception-age milestones in one shared
pipeline, not separate competing execution engines.
