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

        # Ambiguous POST is recovered by a read-only broker lookup in the
        # same attempt. A subsequent restart only reconciles the ledger.
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


@unittest.skipUnless(os.getenv('TEST_PAPER_LEDGER_DATABASE_URL'),
                      'requires disposable PostgreSQL test database')
class AutonomousPaperLedgerIntegrationTests(unittest.TestCase):
    def test_entry_commits_before_post_and_never_reposts_on_restart(self):
        import psycopg
        from unittest.mock import patch
        from uuid import uuid4
        from paper_opportunity_intelligence import submit_durable_paper_order

        dsn = os.environ['TEST_PAPER_LEDGER_DATABASE_URL']
        request_id = 'ho-e2e-' + uuid4().hex
        with psycopg.connect(dsn) as setup:
            setup.execute(DDL)
        posts = []
        def fake_broker(host, path, key, secret, *, params=None, payload=None):
            if path == '/v2/orders:by_client_order_id':
                if posts:
                    return dict(posts[0])
                raise RuntimeError('Alpaca HTTP 404')
            if path == '/v2/account':
                return {'status': 'ACTIVE', 'trading_blocked': False,
                        'account_blocked': False, 'cash': '1000', 'buying_power': '1000'}
            if path == '/v2/assets/SPY':
                return {'status': 'active', 'tradable': True, 'fractionable': True}
            if path == '/v2/orders' and payload is not None:
                with psycopg.connect(dsn) as db:
                    state = db.execute(
                        'SELECT state FROM paper_order_ledger WHERE request_id=%s',
                        (request_id,)).fetchone()[0]
                self.assertEqual(state, 'ATTEMPT_RESERVED')
                response = {'id': 'synthetic-broker-1', 'status': 'accepted',
                            'symbol': 'SPY', 'side': 'buy', 'notional': '10.00',
                            'client_order_id': request_id}
                posts.append(response)
                return response
            self.fail('Unexpected broker path: ' + path)
        original_connect = psycopg.connect
        def local_connect(*args, **kwargs):
            # Test service does not use TLS; production helper demands TLS.
            kwargs.pop('sslmode', None)
            return original_connect(*args, **kwargs)
        try:
            with patch.dict(os.environ, {'PAPER_LEDGER_DATABASE_URL': dsn}):
                with patch('psycopg.connect', side_effect=local_connect):
                    first = submit_durable_paper_order(
                        symbol='SPY', notional=Decimal('10'), request_id=request_id,
                        key='test', secret='test', get=fake_broker)
                    second = submit_durable_paper_order(
                        symbol='SPY', notional=Decimal('10'), request_id=request_id,
                        key='test', secret='test', get=fake_broker)
            self.assertEqual(first['broker_order_id'], 'synthetic-broker-1')
            self.assertTrue(second['reconciled_existing_order'])
            self.assertEqual(len(posts), 1)
            with psycopg.connect(dsn) as db:
                state = db.execute(
                    'SELECT state FROM paper_order_ledger WHERE request_id=%s',
                    (request_id,)).fetchone()[0]
                self.assertEqual(state, 'BROKER_CONFIRMED')
        finally:
            with psycopg.connect(dsn) as cleanup:
                cleanup.execute('DELETE FROM paper_order_ledger WHERE request_id=%s',
                                (request_id,))


if __name__ == '__main__':
    unittest.main()
