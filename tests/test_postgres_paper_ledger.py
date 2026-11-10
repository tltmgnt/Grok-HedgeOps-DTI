"""Offline recovery tests plus opt-in real PostgreSQL concurrency integration.

Set TEST_PAPER_LEDGER_DATABASE_URL to an isolated disposable test database.
No Alpaca network calls are made.
"""
import os
import threading
import unittest
from decimal import Decimal

from postgres_paper_ledger import DDL, LedgerError, PostgresPaperLedger, reconcile_with_ledger, submit_with_ledger

RID = 'hedgeops-ledger-20261110'


class FakeLedger:
    def __init__(self):
        self.seen = False
        self.records = []

    def lock(self, request_id):
        from contextlib import nullcontext
        return nullcontext()

    def reserve(self, request_id, symbol, amount):
        fresh = not self.seen
        self.seen = True
        return fresh

    def record(self, request_id, **kwargs):
        self.records.append(kwargs)


class LedgerRecoveryTests(unittest.TestCase):
    def test_missing_credentials_do_not_reserve_durable_intent(self):
        ledger = FakeLedger()
        with self.assertRaisesRegex(ValueError, 'credentials missing'):
            submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                               key='', secret='', get=lambda *a, **kw: self.fail('broker called'))
        self.assertFalse(ledger.seen)
        self.assertEqual(ledger.records, [])

    def test_restart_reconciles_without_second_post(self):
        ledger = FakeLedger()
        calls = []

        def broker(host, path, key, secret, *, params=None, payload=None):
            calls.append(path)
            if path == '/v2/orders:by_client_order_id':
                if len(calls) == 1:
                    raise RuntimeError('Alpaca HTTP 404')
                return {'id': 'order-1', 'symbol': 'SPY', 'side': 'buy',
                        'notional': '25', 'client_order_id': RID, 'status': 'accepted'}
            if path == '/v2/account':
                return {'status': 'ACTIVE', 'trading_blocked': False,
                        'account_blocked': False, 'cash': '100', 'buying_power': '100'}
            if path == '/v2/assets/SPY':
                return {'status': 'active', 'tradable': True, 'fractionable': True}
            if path == '/v2/orders':
                raise RuntimeError('POST timed out')
            self.fail(path)

        first = submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                                   key='k', secret='s', get=broker)
        self.assertTrue(first['reconciled_existing_order'])
        result = submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                                    key='k', secret='s', get=broker)
        self.assertTrue(result['reconciled_existing_order'])
        self.assertEqual(calls.count('/v2/orders'), 1)
        self.assertTrue(ledger.records[-1]['confirmed'])

    def test_ambiguous_post_acknowledgment_never_reposts(self):
        ledger = FakeLedger()
        calls = []

        def broker(host, path, key, secret, *, params=None, payload=None):
            calls.append(path)
            if path == '/v2/orders:by_client_order_id':
                if calls.count(path) == 1:
                    raise RuntimeError('Alpaca HTTP 404')
                raise RuntimeError('Alpaca HTTP 404')
            if path == '/v2/account':
                return {'status': 'ACTIVE', 'trading_blocked': False,
                        'account_blocked': False, 'cash': '100', 'buying_power': '100'}
            if path == '/v2/assets/SPY':
                return {'status': 'active', 'tradable': True, 'fractionable': True}
            if path == '/v2/orders':
                # A successful HTTP response with malformed evidence is still
                # ambiguous: the broker may have accepted the order.
                return {'id': 'broker-123', 'symbol': 'AAPL', 'side': 'buy',
                        'notional': '25', 'client_order_id': RID, 'status': 'accepted'}
            self.fail(path)

        with self.assertRaisesRegex(RuntimeError, 'Ambiguous broker acknowledgment'):
            submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                               key='k', secret='s', get=broker)
        with self.assertRaisesRegex(LedgerError, 'manual reconciliation'):
            submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                               key='k', secret='s', get=broker)
        self.assertEqual(calls.count('/v2/orders'), 1)
        self.assertFalse(ledger.records[-1]['confirmed'])

    def test_missing_after_crash_never_reposts(self):
        ledger = FakeLedger()
        ledger.seen = True
        calls = []

        def broker(host, path, key, secret, *, params=None, payload=None):
            calls.append(path)
            raise RuntimeError('Alpaca HTTP 404')

        with self.assertRaisesRegex(LedgerError, 'manual reconciliation'):
            submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                               key='k', secret='s', get=broker)
        self.assertEqual(calls, ['/v2/orders:by_client_order_id'])
        self.assertFalse(ledger.records[-1]['confirmed'])


@unittest.skipUnless(os.getenv('TEST_PAPER_LEDGER_DATABASE_URL'),
                     'requires disposable PostgreSQL test database')
class PostgresConcurrencyTests(unittest.TestCase):
    def test_reconcile_only_requires_existing_reservation_and_never_posts(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-reconcile'
        calls = []

        def broker(host, path, key, secret, *, params=None, payload=None):
            calls.append(path)
            if path != '/v2/orders:by_client_order_id':
                raise AssertionError('Reconciliation attempted broker POST')
            return {'id': 'reconciled-123', 'symbol': 'SPY', 'side': 'buy',
                    'notional': '25', 'client_order_id': rid, 'status': 'accepted'}

        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            with self.assertRaisesRegex(LedgerError, 'No durable reservation'):
                reconcile_with_ledger(ledger, 'SPY', Decimal('25'), rid,
                                      key='k', secret='s', get=broker)
            self.assertEqual(calls, [])
            with ledger.lock(rid):
                self.assertTrue(ledger.reserve(rid, 'SPY', Decimal('25')))
            result = reconcile_with_ledger(ledger, 'SPY', Decimal('25'), rid,
                                           key='k', secret='s', get=broker)
            self.assertTrue(result['reconciled_existing_order'])
            self.assertEqual(calls, ['/v2/orders:by_client_order_id'])
            row = conn.execute(
                'SELECT state, broker_order_id FROM paper_order_ledger WHERE request_id=%s',
                (rid,)).fetchone()
            self.assertEqual(row, ('BROKER_CONFIRMED', 'reconciled-123'))
            conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_blank_order_identity_rejected_by_application_and_database(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-blank-identity'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            for request_id, symbol in (('   ', 'SPY'), (rid, '   ')):
                with self.subTest(request_id=request_id, symbol=symbol):
                    with self.assertRaisesRegex(LedgerError, 'request ID or symbol'):
                        ledger.reserve(request_id, symbol, Decimal('25'))
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        conn.execute(
                            """INSERT INTO paper_order_ledger
                               (request_id, symbol, notional_usd, state)
                               VALUES (%s, %s, 25, 'ATTEMPT_RESERVED')""",
                            (request_id, symbol))
                    conn.rollback()
            self.assertIsNone(conn.execute(
                'SELECT request_id FROM paper_order_ledger WHERE request_id=%s',
                (rid,)).fetchone())

    def test_database_rejects_nan_notional_even_from_direct_sql(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-sql-nan'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            with self.assertRaises(psycopg.errors.CheckViolation):
                conn.execute(
                    """INSERT INTO paper_order_ledger
                       (request_id, symbol, notional_usd, state)
                       VALUES (%s, 'SPY', 'NaN'::numeric, 'ATTEMPT_RESERVED')""",
                    (rid,))
            conn.rollback()
            self.assertIsNone(conn.execute(
                'SELECT request_id FROM paper_order_ledger WHERE request_id=%s',
                (rid,)).fetchone())

    def test_invalid_reservation_notional_is_rejected_before_insert(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-precision'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                for amount in (Decimal('25.001'), Decimal('NaN'),
                               Decimal('Infinity'), Decimal('0'),
                               Decimal('-1'), Decimal('10000000000')):
                    with self.subTest(amount=str(amount)):
                        with ledger.lock(rid):
                            with self.assertRaisesRegex(LedgerError, 'notional'):
                                ledger.reserve(rid, 'SPY', amount)
                self.assertIsNone(conn.execute(
                    'SELECT request_id FROM paper_order_ledger WHERE request_id=%s',
                    (rid,)).fetchone())
                with ledger.lock(rid):
                    self.assertTrue(ledger.reserve(rid, 'SPY', Decimal('25.01')))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_reservation_creation_time_cannot_be_rewritten(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-created-at'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                original = conn.execute(
                    'SELECT created_at FROM paper_order_ledger WHERE request_id=%s',
                    (rid,)).fetchone()[0]
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(
                        "UPDATE paper_order_ledger "
                        "SET created_at = created_at - interval '1 day' "
                        "WHERE request_id=%s", (rid,))
                conn.rollback()
                actual = conn.execute(
                    'SELECT created_at FROM paper_order_ledger WHERE request_id=%s',
                    (rid,)).fetchone()[0]
                self.assertEqual(actual, original)
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_terminal_broker_statuses_reject_stale_updates(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            for status in ('filled', 'canceled', 'expired', 'rejected'):
                rid = RID + '-terminal-' + status
                try:
                    with ledger.lock(rid):
                        ledger.reserve(rid, 'SPY', Decimal('25'))
                        ledger.record(rid, confirmed=True,
                                      broker_order_id='terminal-' + status,
                                      broker_status=status)
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            ledger.record(rid, confirmed=True,
                                          broker_order_id='terminal-' + status,
                                          broker_status='accepted')
                    row = conn.execute(
                        'SELECT broker_status FROM paper_order_ledger '
                        'WHERE request_id=%s', (rid,)).fetchone()
                    self.assertEqual(row, (status,))
                finally:
                    conn.rollback()
                    conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))
                    conn.commit()

    def test_reinitializing_ddl_preserves_confirmed_guard(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-guard-reinit'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    ledger.record(rid, confirmed=True,
                                  broker_order_id='guard-reinit-order',
                                  broker_status='filled')
                # A second startup replaces the trigger without a DROP window.
                conn.execute(DDL)
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(
                        "UPDATE paper_order_ledger SET symbol='AAPL' "
                        "WHERE request_id=%s", (rid,))
                conn.rollback()
                row = conn.execute(
                    'SELECT symbol, broker_status FROM paper_order_ledger '
                    'WHERE request_id=%s', (rid,)).fetchone()
                self.assertEqual(row, ('SPY', 'filled'))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_unconfirmed_row_cannot_claim_broker_evidence(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-unconfirmed-evidence'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    ledger.record(rid, confirmed=False)
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(
                        """UPDATE paper_order_ledger
                           SET broker_order_id='unverified-id', broker_status='accepted'
                           WHERE request_id=%s""", (rid,))
                conn.rollback()
                row = conn.execute(
                    'SELECT state, broker_order_id, broker_status '
                    'FROM paper_order_ledger WHERE request_id=%s', (rid,)).fetchone()
                self.assertEqual(row, ('BROKER_UNCONFIRMED', None, None))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_filled_status_cannot_regress_on_stale_reconciliation(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-filled'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    ledger.record(rid, confirmed=True,
                                  broker_order_id='filled-order', broker_status='filled')
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        ledger.record(rid, confirmed=True,
                                      broker_order_id='filled-order', broker_status='accepted')
                    # A PostgreSQL constraint violation aborts the transaction.
                    # Reset it before inspecting the previously committed row.
                    conn.rollback()
                    # The rejected update must not change the durable evidence.
                    row = conn.execute(
                        'SELECT state, broker_order_id, broker_status '
                        'FROM paper_order_ledger WHERE request_id=%s',
                        (rid,)).fetchone()
                    self.assertEqual(row, ('BROKER_CONFIRMED', 'filled-order', 'filled'))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_confirmed_order_status_can_progress_without_changing_identity(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-progress'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    ledger.record(rid, confirmed=True,
                                  broker_order_id='progress-order', broker_status='accepted')
                    ledger.record(rid, confirmed=True,
                                  broker_order_id='progress-order', broker_status='filled')
                row = conn.execute(
                    'SELECT state, broker_order_id, broker_status FROM paper_order_ledger '
                    'WHERE request_id=%s', (rid,)).fetchone()
                self.assertEqual(row, ('BROKER_CONFIRMED', 'progress-order', 'filled'))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_unconfirmed_attempt_cannot_be_reset_to_reserved(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-no-reset'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    ledger.record(rid, confirmed=False)
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(
                        "UPDATE paper_order_ledger SET state='ATTEMPT_RESERVED' "
                        "WHERE request_id=%s", (rid,))
                conn.rollback()
                row = conn.execute(
                    'SELECT state FROM paper_order_ledger WHERE request_id=%s',
                    (rid,)).fetchone()
                self.assertEqual(row, ('BROKER_UNCONFIRMED',))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_direct_sql_cannot_rewrite_reserved_intent(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-intent'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                for field, value in (
                    ('request_id', rid + '-new'),
                    ('symbol', 'AAPL'),
                    ('notional_usd', Decimal('26')),
                ):
                    with self.subTest(field=field):
                        # Field names are fixed test literals, not user input.
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            conn.execute(
                                f'UPDATE paper_order_ledger SET {field}=%s WHERE request_id=%s',
                                (value, rid))
                        conn.rollback()
                row = conn.execute(
                    'SELECT request_id, symbol, notional_usd FROM paper_order_ledger '
                    'WHERE request_id=%s', (rid,)).fetchone()
                self.assertEqual(row, (rid, 'SPY', Decimal('25')))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_direct_sql_cannot_downgrade_confirmed_order(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-immutable'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    ledger.record(rid, confirmed=True,
                                  broker_order_id='immutable-order', broker_status='accepted')
                for statement, value in (
                    ('UPDATE paper_order_ledger SET state=%s WHERE request_id=%s',
                     'BROKER_UNCONFIRMED'),
                    ('UPDATE paper_order_ledger SET broker_order_id=%s WHERE request_id=%s',
                     'replacement-order'),
                ):
                    with self.subTest(value=value):
                        with self.assertRaises(psycopg.errors.CheckViolation):
                            conn.execute(statement, (value, rid))
                        conn.rollback()
                row = conn.execute(
                    'SELECT state, broker_order_id FROM paper_order_ledger WHERE request_id=%s',
                    (rid,)).fetchone()
                self.assertEqual(row, ('BROKER_CONFIRMED', 'immutable-order'))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_migration_fails_closed_on_invalid_historical_confirmation(self):
        import psycopg
        from psycopg import sql
        from uuid import uuid4
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        schema = 'ledger_invalid_' + uuid4().hex
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.commit()
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                conn.execute(
                    """CREATE TABLE paper_order_ledger (
                       request_id varchar(48) PRIMARY KEY,
                       symbol varchar(15) NOT NULL,
                       notional_usd numeric(12,2) NOT NULL,
                       state text NOT NULL,
                       broker_order_id text,
                       broker_status text,
                       created_at timestamptz DEFAULT now(),
                       updated_at timestamptz DEFAULT now())""")
                conn.execute(
                    """INSERT INTO paper_order_ledger
                       (request_id, symbol, notional_usd, state)
                       VALUES ('legacy-invalid', 'SPY', 25, 'BROKER_CONFIRMED')""")
                conn.commit()
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(DDL)
                conn.rollback()
                row = conn.execute(
                    'SELECT state, broker_order_id FROM paper_order_ledger '
                    'WHERE request_id=%s', ('legacy-invalid',)).fetchone()
                self.assertEqual(row, ('BROKER_CONFIRMED', None))
            finally:
                conn.rollback()
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    def test_ddl_upgrades_existing_ledger_table(self):
        import psycopg
        from psycopg import sql
        from uuid import uuid4
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        schema = 'ledger_migration_' + uuid4().hex
        with psycopg.connect(dsn) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                # Simulate a deployment created before the confirmation check.
                conn.execute(
                    """CREATE TABLE paper_order_ledger (
                       request_id varchar(48) PRIMARY KEY,
                       symbol varchar(15) NOT NULL,
                       notional_usd numeric(12,2) NOT NULL,
                       state text NOT NULL,
                       broker_order_id text,
                       broker_status text,
                       created_at timestamptz DEFAULT now(),
                       updated_at timestamptz DEFAULT now())""")
                conn.execute(DDL)
                conn.execute(DDL)  # Migration must be idempotent.
                conn.commit()  # Keep the disposable schema after the expected rollback.
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(
                        """INSERT INTO paper_order_ledger
                           (request_id, symbol, notional_usd, state)
                           VALUES ('invalid-confirmation', 'SPY', 25, 'BROKER_CONFIRMED')""")
                conn.rollback()
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    def test_database_rejects_confirmed_rows_without_broker_evidence(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-sql-guard'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            # PostgreSQL rolls back transactional DDL too. Preserve the
            # schema before intentionally provoking a CHECK violation.
            conn.commit()
            try:
                with self.assertRaises(psycopg.errors.CheckViolation):
                    conn.execute(
                        """INSERT INTO paper_order_ledger
                           (request_id, symbol, notional_usd, state)
                           VALUES (%s, 'SPY', 25, 'BROKER_CONFIRMED')""",
                        (rid,),
                    )
                conn.rollback()
                row = conn.execute(
                    'SELECT request_id FROM paper_order_ledger WHERE request_id=%s',
                    (rid,),
                ).fetchone()
                self.assertIsNone(row)
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_confirmation_requires_complete_broker_evidence(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-evidence'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(rid):
                    ledger.reserve(rid, 'SPY', Decimal('25'))
                    for order_id, status in ((None, 'accepted'), ('', 'accepted'),
                                             ('order-1', None), ('order-1', '')):
                        with self.subTest(order_id=order_id, status=status):
                            with self.assertRaisesRegex(LedgerError, 'requires order ID and status'):
                                ledger.record(rid, confirmed=True,
                                              broker_order_id=order_id,
                                              broker_status=status)
                    row = conn.execute(
                        'SELECT state, broker_order_id, broker_status '
                        'FROM paper_order_ledger WHERE request_id=%s', (rid,)).fetchone()
                    self.assertEqual(row, ('ATTEMPT_RESERVED', None, None))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_broker_order_id_cannot_belong_to_two_requests(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        first = RID + '-unique-a'
        second = RID + '-unique-b'
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            try:
                with ledger.lock(first):
                    ledger.reserve(first, 'SPY', Decimal('25'))
                    ledger.record(first, confirmed=True, broker_order_id='shared-order-id',
                                  broker_status='accepted')
                with ledger.lock(second):
                    ledger.reserve(second, 'SPY', Decimal('25'))
                    with self.assertRaises(psycopg.errors.UniqueViolation):
                        ledger.record(second, confirmed=True,
                                      broker_order_id='shared-order-id',
                                      broker_status='accepted')
                row = conn.execute(
                    'SELECT state, broker_order_id FROM paper_order_ledger WHERE request_id=%s',
                    (second,)).fetchone()
                self.assertEqual(row, ('ATTEMPT_RESERVED', None))
            finally:
                conn.rollback()
                conn.execute('DELETE FROM paper_order_ledger WHERE request_id IN (%s, %s)',
                             (first, second))

    def test_failed_transaction_releases_session_lock(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        with psycopg.connect(dsn) as conn:
            conn.execute(DDL)
            ledger = PostgresPaperLedger(conn)
            with self.assertRaises(psycopg.errors.UndefinedTable):
                with ledger.lock(RID + '-failed'):
                    conn.execute('SELECT * FROM table_that_does_not_exist_ledger')
            # If the lock leaked, a separate session could not acquire it.
            with psycopg.connect(dsn) as other:
                with PostgresPaperLedger(other).lock(RID + '-failed'):
                    pass

    def test_two_runners_cannot_double_post(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        rid = RID + '-race'
        with psycopg.connect(dsn) as setup:
            setup.execute(DDL)
        posting = threading.Event()
        release = threading.Event()
        calls = []
        errors = []

        def broker(host, path, key, secret, *, params=None, payload=None):
            if path == '/v2/orders:by_client_order_id':
                if not posting.is_set():
                    raise RuntimeError('Alpaca HTTP 404')
                return {'id': 'race-order', 'symbol': 'SPY', 'side': 'buy',
                        'notional': '25', 'client_order_id': rid, 'status': 'accepted'}
            if path == '/v2/account':
                return {'status': 'ACTIVE', 'trading_blocked': False,
                        'account_blocked': False, 'cash': '100', 'buying_power': '100'}
            if path == '/v2/assets/SPY':
                return {'status': 'active', 'tradable': True, 'fractionable': True}
            if path == '/v2/orders':
                calls.append(path)
                posting.set()
                if not release.wait(timeout=10):
                    raise RuntimeError('Timed out waiting for test release')
                return {'id': 'race-order', 'symbol': 'SPY', 'side': 'buy',
                        'notional': '25', 'client_order_id': rid, 'status': 'accepted'}
            raise AssertionError(path)

        def first_runner():
            try:
                with psycopg.connect(dsn) as conn:
                    submit_with_ledger(PostgresPaperLedger(conn), 'SPY',
                                       Decimal('25'), rid, key='k', secret='s', get=broker)
            except Exception as exc:
                errors.append(exc)
                posting.set()

        thread = threading.Thread(target=first_runner)
        thread.start()
        try:
            self.assertTrue(posting.wait(timeout=10))
            self.assertFalse(errors)
            with psycopg.connect(dsn) as conn:
                with self.assertRaisesRegex(LedgerError, 'Another runner'):
                    submit_with_ledger(PostgresPaperLedger(conn), 'SPY',
                                       Decimal('25'), rid, key='k', secret='s', get=broker)
            release.set()
            thread.join(timeout=10)
            self.assertFalse(errors)
            with psycopg.connect(dsn) as conn:
                result = submit_with_ledger(PostgresPaperLedger(conn), 'SPY',
                                            Decimal('25'), rid, key='k', secret='s', get=broker)
                self.assertTrue(result['reconciled_existing_order'])
            self.assertEqual(calls, ['/v2/orders'])
        finally:
            release.set()
            thread.join(timeout=10)
            with psycopg.connect(dsn) as cleanup:
                cleanup.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (rid,))

    def test_cross_connection_lock_and_durable_reservation(self):
        import psycopg
        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        with psycopg.connect(dsn) as setup:
            setup.execute(DDL)
        started = threading.Event()
        release = threading.Event()
        failures = []

        def holder():
            try:
                with psycopg.connect(dsn) as conn:
                    ledger = PostgresPaperLedger(conn)
                    with ledger.lock(RID):
                        ledger.reserve(RID, 'SPY', Decimal('25'))
                        started.set()
                        release.wait(timeout=10)
            except Exception as exc:
                failures.append(exc)
                started.set()

        thread = threading.Thread(target=holder)
        thread.start()
        try:
            self.assertTrue(started.wait(timeout=10))
            self.assertFalse(failures)
            with psycopg.connect(dsn) as conn:
                ledger = PostgresPaperLedger(conn)
                with self.assertRaisesRegex(LedgerError, 'Another runner'):
                    with ledger.lock(RID):
                        pass
            release.set()
            thread.join(timeout=10)
            self.assertFalse(failures)
            with psycopg.connect(dsn) as conn:
                ledger = PostgresPaperLedger(conn)
                with ledger.lock(RID):
                    ledger.record(RID, confirmed=True,
                                  broker_order_id='paper-123', broker_status='accepted')
                    ledger.record(RID, confirmed=False)
                    row = conn.execute(
                        'SELECT state, broker_order_id FROM paper_order_ledger WHERE request_id=%s',
                        (RID,)).fetchone()
                    self.assertEqual(row, ('BROKER_CONFIRMED', 'paper-123'))
                    with self.assertRaisesRegex(LedgerError, 'broker order ID conflict'):
                        ledger.record(RID, confirmed=True,
                                      broker_order_id='different-order', broker_status='filled')
                    row = conn.execute(
                        'SELECT state, broker_order_id, broker_status '
                        'FROM paper_order_ledger WHERE request_id=%s',
                        (RID,)).fetchone()
                    self.assertEqual(row, ('BROKER_CONFIRMED', 'paper-123', 'accepted'))
            with psycopg.connect(dsn) as conn:
                ledger = PostgresPaperLedger(conn)
                with ledger.lock(RID):
                    self.assertFalse(ledger.reserve(RID, 'SPY', Decimal('25')))
                    with self.assertRaisesRegex(LedgerError, 'different order'):
                        ledger.reserve(RID, 'AAPL', Decimal('25'))
        finally:
            release.set()
            thread.join(timeout=10)
            with psycopg.connect(dsn) as cleanup:
                cleanup.execute('DELETE FROM paper_order_ledger WHERE request_id=%s', (RID,))


if __name__ == '__main__':
    unittest.main()
