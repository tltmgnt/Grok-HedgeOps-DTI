"""PostgreSQL-backed fail-closed PAPER order ledger.

Requires psycopg 3 and a durable PostgreSQL database. An attempt is committed
BEFORE any broker POST. Existing attempts can only be reconciled, never posted
again. Session advisory locks serialize concurrent runners per request ID.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal

DDL = """
CREATE TABLE IF NOT EXISTS paper_order_ledger (
    request_id varchar(48) PRIMARY KEY,
    symbol varchar(15) NOT NULL,
    notional_usd numeric(12,2) NOT NULL CHECK (notional_usd > 0),
    state text NOT NULL CHECK (state IN
        ('ATTEMPT_RESERVED','BROKER_UNCONFIRMED','BROKER_CONFIRMED')),
    broker_order_id text,
    broker_status text,
    CONSTRAINT paper_order_ledger_confirmed_evidence CHECK (
        state <> 'BROKER_CONFIRMED' OR (
            broker_order_id IS NOT NULL AND length(btrim(broker_order_id)) > 0
            AND broker_status IS NOT NULL AND length(btrim(broker_status)) > 0
        )
    ),
    CONSTRAINT paper_order_ledger_evidence_consistency CHECK (
        state = 'BROKER_CONFIRMED'
        OR (broker_order_id IS NULL AND broker_status IS NULL)
    ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- CREATE TABLE IF NOT EXISTS does not upgrade older tables. Enforce the
-- invariant for pre-existing deployments as well; invalid historical rows
-- cause startup to fail closed until an operator reconciles them.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'paper_order_ledger'::regclass
          AND conname = 'paper_order_ledger_confirmed_evidence'
    ) THEN
        ALTER TABLE paper_order_ledger
        ADD CONSTRAINT paper_order_ledger_confirmed_evidence CHECK (
            state <> 'BROKER_CONFIRMED' OR (
                broker_order_id IS NOT NULL AND length(btrim(broker_order_id)) > 0
                AND broker_status IS NOT NULL AND length(btrim(broker_status)) > 0
            )
        );
    END IF;
END $$;
-- Protect confirmed evidence against direct SQL updates and other writers.
CREATE OR REPLACE FUNCTION paper_order_ledger_guard_confirmed()
RETURNS trigger LANGUAGE plpgsql AS $guard$
BEGIN
    -- The request ID, symbol and notional define the original durable intent.
    -- They must not be reassigned, even while an order is unconfirmed.
    IF NEW.request_id IS DISTINCT FROM OLD.request_id
       OR NEW.symbol IS DISTINCT FROM OLD.symbol
       OR NEW.notional_usd IS DISTINCT FROM OLD.notional_usd THEN
        RAISE EXCEPTION 'Reserved order intent cannot be changed'
            USING ERRCODE = '23514';
    END IF;
    -- Once a submission has become ambiguous, reverting to RESERVED would
    -- falsely suggest that no broker attempt has happened.
    IF OLD.state = 'BROKER_UNCONFIRMED'
       AND NEW.state = 'ATTEMPT_RESERVED' THEN
        RAISE EXCEPTION 'Unconfirmed broker attempt cannot become reserved again'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.state = 'BROKER_CONFIRMED' AND (
        NEW.state <> 'BROKER_CONFIRMED'
        OR NEW.broker_order_id IS DISTINCT FROM OLD.broker_order_id
    ) THEN
        RAISE EXCEPTION 'Confirmed broker identity cannot be changed'
            USING ERRCODE = '23514';
    END IF;
    -- A filled order is terminal: stale reconciliation must not erase
    -- evidence of execution by restoring an earlier broker status.
    IF OLD.state = 'BROKER_CONFIRMED'
       AND OLD.broker_status = 'filled'
       AND NEW.broker_status IS DISTINCT FROM 'filled' THEN
        RAISE EXCEPTION 'Filled broker status cannot regress'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$guard$;
-- Replace atomically: dropping then recreating leaves a window without
-- protection and can race with another runner initializing the ledger.
CREATE OR REPLACE TRIGGER paper_order_ledger_confirmed_guard
BEFORE UPDATE ON paper_order_ledger
FOR EACH ROW EXECUTE FUNCTION paper_order_ledger_guard_confirmed();
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'paper_order_ledger'::regclass
          AND conname = 'paper_order_ledger_evidence_consistency'
    ) THEN
        ALTER TABLE paper_order_ledger
        ADD CONSTRAINT paper_order_ledger_evidence_consistency CHECK (
            state = 'BROKER_CONFIRMED'
            OR (broker_order_id IS NULL AND broker_status IS NULL)
        );
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS paper_order_ledger_broker_order_id_unique
    ON paper_order_ledger (broker_order_id)
    WHERE broker_order_id IS NOT NULL;
"""


class LedgerError(RuntimeError):
    pass


class PostgresPaperLedger:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def lock(self, request_id):
        """Session-scoped lock, held through submission and status persistence."""
        with self.connection.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0))", (request_id,))
            acquired = cur.fetchone()[0]
        if not acquired:
            self.connection.rollback()
            raise LedgerError('Another runner owns this request ID; reconcile later')
        try:
            yield
        finally:
            # A failed statement aborts the current transaction, but the
            # session advisory lock remains held. Roll back before unlocking.
            self.connection.rollback()
            with self.connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (request_id,))
                if cur.fetchone()[0] is not True:
                    raise LedgerError('Lost PostgreSQL advisory lock ownership')
            self.connection.commit()

    def reserve(self, request_id, symbol, amount):
        """Return True only for a newly committed intent; never reset old rows."""
        with self.connection.cursor() as cur:
            cur.execute(
                """INSERT INTO paper_order_ledger
                   (request_id, symbol, notional_usd, state)
                   VALUES (%s, %s, %s, 'ATTEMPT_RESERVED')
                   ON CONFLICT (request_id) DO NOTHING
                   RETURNING request_id""",
                (request_id, symbol, amount),
            )
            inserted = cur.fetchone() is not None
            cur.execute(
                "SELECT symbol, notional_usd FROM paper_order_ledger WHERE request_id=%s",
                (request_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] != symbol or Decimal(str(row[1])) != amount:
            self.connection.rollback()
            raise LedgerError('Request ID already bound to a different order')
        self.connection.commit()  # Durable before any network POST.
        return inserted

    def record(self, request_id, *, confirmed, broker_order_id=None, broker_status=None):
        # A confirmed row must always have usable broker evidence. Never let a
        # caller mark a reservation confirmed with a missing/blank identity.
        if confirmed and (not isinstance(broker_order_id, str)
                          or not broker_order_id.strip()
                          or not isinstance(broker_status, str)
                          or not broker_status.strip()):
            raise LedgerError('Broker confirmation requires order ID and status')
        if not confirmed and (broker_order_id is not None or broker_status is not None):
            raise LedgerError('Unconfirmed record cannot supply broker evidence')
        state = 'BROKER_CONFIRMED' if confirmed else 'BROKER_UNCONFIRMED'
        with self.connection.cursor() as cur:
            cur.execute(
                """UPDATE paper_order_ledger
                   SET state=CASE WHEN state='BROKER_CONFIRMED'
                                  THEN state ELSE %s END,
                       broker_order_id=COALESCE(broker_order_id, %s),
                       broker_status=CASE
                           WHEN %s = 'BROKER_UNCONFIRMED' THEN broker_status
                           ELSE %s END,
                       updated_at=now()
                   WHERE request_id=%s
                     AND (broker_order_id IS NULL OR %s::text IS NULL
                          OR broker_order_id=%s)""",
                (state, broker_order_id, state, broker_status, request_id,
                 broker_order_id, broker_order_id),
            )
            if cur.rowcount != 1:
                self.connection.rollback()
                raise LedgerError('Ledger row missing or broker order ID conflict')
        self.connection.commit()



def reconcile_with_ledger(ledger, symbol, amount, request_id, *, key, secret, get):
    """Read-only broker reconciliation of a previously reserved request ID.

    Never creates a reservation or issues a broker POST. A missing ledger row
    is an error, not proof that an order was never sent.
    """
    from paper_opportunity_intelligence import PAPER
    from paper_purchase_decision import acknowledgment

    if not key or not secret:
        raise ValueError('Paper credentials missing')
    with ledger.lock(request_id):
        with ledger.connection.cursor() as cur:
            cur.execute(
                'SELECT symbol, notional_usd FROM paper_order_ledger WHERE request_id=%s',
                (request_id,),
            )
            row = cur.fetchone()
        ledger.connection.rollback()
        if row is None:
            raise LedgerError('No durable reservation for request ID; cannot reconcile')
        if row[0] != symbol or Decimal(str(row[1])) != amount:
            raise LedgerError('Request ID already bound to a different order')
        try:
            order = get(PAPER, '/v2/orders:by_client_order_id', key, secret,
                        params={'client_order_id': request_id})
            result = acknowledgment(order, symbol, amount, request_id, existing=True)
        except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
            ledger.record(request_id, confirmed=False)
            raise LedgerError('Prior attempt unresolved; manual reconciliation required') from exc
        ledger.record(request_id, confirmed=True,
                      broker_order_id=result['broker_order_id'],
                      broker_status=result['broker_status'])
        return result


def submit_with_ledger(ledger, symbol, amount, request_id, *, key, secret, get):
    """Use broker as source of truth; no second POST for existing ledger rows."""
    from paper_opportunity_intelligence import PAPER
    from paper_purchase_decision import acknowledgment, submit

    # Missing credentials are a configuration failure, not an attempted order.
    # Do not poison a durable request ID before any broker interaction is possible.
    if not key or not secret:
        raise ValueError('Paper credentials missing')

    with ledger.lock(request_id):
        first_attempt = ledger.reserve(request_id, symbol, amount)
        if not first_attempt:
            # A crash may have happened before, during or after POST.
            # 404 does NOT prove it is safe to submit again.
            try:
                order = get(PAPER, '/v2/orders:by_client_order_id', key, secret,
                            params={'client_order_id': request_id})
                result = acknowledgment(order, symbol, amount, request_id, existing=True)
            except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
                ledger.record(request_id, confirmed=False)
                raise LedgerError('Prior attempt unresolved; manual reconciliation required') from exc
        else:
            try:
                result = submit(symbol, amount, request_id, key=key, secret=secret, get=get)
            except (RuntimeError, ValueError, KeyError, TypeError, OSError):
                ledger.record(request_id, confirmed=False)
                raise
        ledger.record(request_id, confirmed=True,
                      broker_order_id=result['broker_order_id'],
                      broker_status=result['broker_status'])
        return result
