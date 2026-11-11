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
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS paper_exit_ledger (
    request_id varchar(48) PRIMARY KEY,
    symbol varchar(15) NOT NULL,
    quantity numeric(20,8) NOT NULL CHECK (quantity > 0),
    state text NOT NULL CHECK (state IN
        ('ATTEMPT_RESERVED','BROKER_UNCONFIRMED','BROKER_CONFIRMED')),
    broker_order_id text,
    broker_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
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
            raise LedgerError('Another runner owns this request ID; reconcile later')
        try:
            yield
        finally:
            with self.connection.cursor() as cur:
                cur.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (request_id,))

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
        state = 'BROKER_CONFIRMED' if confirmed else 'BROKER_UNCONFIRMED'
        with self.connection.cursor() as cur:
            cur.execute(
                """UPDATE paper_order_ledger SET state=%s, broker_order_id=%s,
                   broker_status=%s, updated_at=now() WHERE request_id=%s""",
                (state, broker_order_id, broker_status, request_id),
            )
            if cur.rowcount != 1:
                self.connection.rollback()
                raise LedgerError('Ledger row missing')
        self.connection.commit()


def submit_with_ledger(ledger, symbol, amount, request_id, *, key, secret, get):
    """Use broker as source of truth; no second POST for existing ledger rows."""
    from paper_opportunity_intelligence import PAPER
    from paper_purchase_decision import acknowledgment, submit

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


class PostgresPaperExitLedger(PostgresPaperLedger):
    """Durable, independent sell-intent ledger; same session-lock semantics."""

    def reserve(self, request_id, symbol, quantity):
        with self.connection.cursor() as cur:
            cur.execute(
                """INSERT INTO paper_exit_ledger (request_id, symbol, quantity, state)
                   VALUES (%s, %s, %s, 'ATTEMPT_RESERVED')
                   ON CONFLICT (request_id) DO NOTHING
                   RETURNING request_id""",
                (request_id, symbol, quantity),
            )
            inserted = cur.fetchone() is not None
            cur.execute(
                "SELECT symbol, quantity FROM paper_exit_ledger WHERE request_id=%s",
                (request_id,),
            )
            row = cur.fetchone()
        if row is None or row[0] != symbol or Decimal(str(row[1])) != quantity:
            self.connection.rollback()
            raise LedgerError("Exit ID already bound to a different order")
        self.connection.commit()  # Durable before broker sell POST.
        return inserted

    def record(self, request_id, *, confirmed, broker_order_id=None, broker_status=None):
        state = 'BROKER_CONFIRMED' if confirmed else 'BROKER_UNCONFIRMED'
        with self.connection.cursor() as cur:
            cur.execute(
                """UPDATE paper_exit_ledger SET state=%s, broker_order_id=%s,
                   broker_status=%s, updated_at=now() WHERE request_id=%s""",
                (state, broker_order_id, broker_status, request_id),
            )
            if cur.rowcount != 1:
                self.connection.rollback()
                raise LedgerError("Exit ledger row missing")
        self.connection.commit()


def submit_exit_with_ledger(ledger, payload, *, key, secret, get):
    """At most one sell POST per persistent exit ID, including after crashes."""
    from paper_opportunity_intelligence import PAPER, money

    request_id, symbol = payload["client_order_id"], payload["symbol"]
    quantity = Decimal(str(payload["qty"]))
    if not quantity.is_finite() or quantity <= 0 or payload.get("side") != "sell":
        raise LedgerError("Unsafe exit parameters")
    with ledger.lock(request_id):
        first_attempt = ledger.reserve(request_id, symbol, quantity)
        if not first_attempt:
            # A 404 after a previous reservation is AMBIGUOUS, never approval
            # to send another sell order. Recovery is read-only.
            try:
                order = get(PAPER, "/v2/orders:by_client_order_id", key, secret,
                            params={"client_order_id": request_id})
            except (RuntimeError, ValueError, KeyError, TypeError, OSError) as exc:
                ledger.record(request_id, confirmed=False)
                raise LedgerError("Prior exit unresolved; manual reconciliation required") from exc
        else:
            try:
                order = get(PAPER, "/v2/orders", key, secret, payload=payload)
            except (RuntimeError, ValueError, KeyError, TypeError, OSError):
                ledger.record(request_id, confirmed=False)
                raise
        if (not isinstance(order, dict) or not order.get("id")
                or any(order.get(k) != payload[k]
                       for k in ("symbol", "side", "client_order_id"))
                or money(order.get("qty")) != money(payload["qty"])):
            ledger.record(request_id, confirmed=False)
            raise LedgerError("Ambiguous exit acknowledgment; reconcile manually")
        ledger.record(request_id, confirmed=True,
                      broker_order_id=order["id"],
                      broker_status=order.get("status"))
        return order
