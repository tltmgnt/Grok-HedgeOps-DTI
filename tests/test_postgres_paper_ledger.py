"""Offline recovery tests plus opt-in real PostgreSQL concurrency integration.

Set TEST_PAPER_LEDGER_DATABASE_URL to an isolated disposable test database.
No Alpaca network calls are made.
"""
import os
import threading
import unittest
from decimal import Decimal

from postgres_paper_ledger import DDL, LedgerError, PostgresPaperLedger, reconcile_with_ledger, submit_with_ledger

RID = 'hedgeops-ledger-test-20261110'


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
