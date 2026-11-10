"""Offline recovery tests plus opt-in real PostgreSQL concurrency integration.

Set TEST_PAPER_LEDGER_DATABASE_URL to an isolated disposable test database.
No Alpaca network calls are made.
"""
import os
import threading
import unittest
from decimal import Decimal

from postgres_paper_ledger import DDL, LedgerError, PostgresPaperLedger, submit_with_ledger

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

        with self.assertRaises(RuntimeError):
            submit_with_ledger(ledger, 'SPY', Decimal('25'), RID, key='k', secret='s', get=broker)
        result = submit_with_ledger(ledger, 'SPY', Decimal('25'), RID,
                                    key='k', secret='s', get=broker)
        self.assertTrue(result['reconciled_existing_order'])
        self.assertEqual(calls.count('/v2/orders'), 1)

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
