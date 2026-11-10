# PostgreSQL PAPER ledger: recovery and migration runbook

This ledger is for **Alpaca PAPER only**. It is not authorization to place
live orders. Keep live trading disabled and PR #71 unmerged until separately
approved.

## Before deployment

1. Use a durable PostgreSQL database with backups, TLS and restricted
   credentials. Do not use an ephemeral CI database in production.
2. Take a restorable database backup before applying the ledger DDL.
3. Stop PAPER order-submitting runners during schema migration. Apply the DDL
   once under operator supervision; verify all constraints and the update
   trigger are present before restarting runners.
4. If migration fails on an invalid historical row, **do not** delete or
   overwrite that row to make the migration pass. Preserve the evidence,
   investigate it against the broker, and obtain explicit operator approval
   for any corrective data migration.
5. Run the PostgreSQL integration suite against a separate disposable database
   using `TEST_PAPER_LEDGER_DATABASE_URL`. Never point tests at the ledger
   used for real PAPER submissions: tests create and delete records.

## Ambiguous submissions

A committed `ATTEMPT_RESERVED` row means a broker POST **may** have occurred.
`BROKER_UNCONFIRMED` means its outcome remains unresolved. Neither state
authorizes a second POST for the same request ID.

1. Stop automatic submission for the affected request ID.
2. Inspect the ledger row (request ID, symbol, amount, state, timestamps).
3. Check Alpaca **PAPER** orders by the exact `client_order_id`, including
   recent orders and any delayed broker visibility. A 404 or timeout is **not**
   evidence that no order was placed.
4. Use the application's `--reconcile-only` path for a read-only broker
   lookup of an existing reservation. It must not issue a broker POST.
5. If evidence remains incomplete or conflicts with the ledger, leave the
   order unresolved, preserve logs, and escalate for manual investigation.
   Do not reset state to `ATTEMPT_RESERVED` or reuse the request ID.

## Confirmed orders

A `BROKER_CONFIRMED` record must contain a nonblank broker order ID and
status. Request ID, symbol, notional, creation timestamp, and broker identity
are immutable. Terminal statuses (`filled`, `canceled`, `expired`,
`rejected`) cannot be overwritten by stale status observations. A
`partially_filled` order cannot revert to a pre-fill status.

A broker-side cancellation, fill, or rejection is **not** equivalent to
permission to place a replacement order. Any replacement requires a separately
reviewed decision and a new, uniquely identified intent.

## Operational boundaries

The ledger is a duplicate-POST safety mechanism, **not** a complete execution
audit or portfolio reconciliation system. Review broker fills, positions,
cash, and exceptions independently. Do not interpret a green CI run as
permission to enable live trading or merge the draft PR.
