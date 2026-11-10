# PostgreSQL paper order ledger (draft deployment gate)

**No live trading is enabled by this change.** Only the manual Alpaca PAPER
submission path is gated. Broker credentials are not stored in PostgreSQL.

## Database preparation

Provision a private, durable PostgreSQL instance with backups, TLS, restricted
network access and a least-privilege application role. Apply the `DDL` string
from `postgres_paper_ledger.py` as a controlled migration before enabling any
paper order workflow. Set the protected GitHub environment secret
`PAPER_LEDGER_DATABASE_URL` to a PostgreSQL connection URI. The application
requires TLS (`sslmode=require`) and fails closed when the URL is absent.

The ledger's primary key is the stable `request_id`. Its first insertion
commits **before** a broker POST. Replays cannot issue a new POST, including
after a crash. Instead they read the broker by `client_order_id`; a missing
order remains unresolved and requires human investigation. Session advisory
locks prevent concurrent runs with the same request ID from entering the
submission/reconciliation critical section at the same time.

## Test and release gates

Run `python -m unittest discover -s tests -p 'test_postgres_paper_ledger.py' -v`
with `TEST_PAPER_LEDGER_DATABASE_URL` pointing to a disposable PostgreSQL
database. CI provisions PostgreSQL 16 and exercises two separate connections,
restart reconciliation, conflicting intents and timeout handling. This test
database must never contain production or real trading data.

## Remaining risks

- PostgreSQL durability, failover, backup restore and TLS identity verification
  require infrastructure acceptance. `sslmode=require` encrypts traffic but
  does not independently prove server identity; use a trusted CA and
  `verify-full` for production.
- A lost connection after an order POST may leave an ambiguous broker outcome.
  The ledger must **never** authorize an automatic replacement order based on
  a broker 404.
- A crash after a ledger reservation but before POST also requires human
  reconciliation; safety is prioritized over automatic liveness.
- An external operator can place broker orders outside this application.
- Database advisory locking is per PostgreSQL cluster and request ID; all
  submission entrypoints must use the same database and canonical IDs.
- This PR does not implement automatic recovery workers, alert delivery,
  real-provider acceptance, live deployment, or proven investment performance.
