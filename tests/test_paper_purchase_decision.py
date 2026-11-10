"""Manual paper purchase contracts; no real network calls or broker orders."""
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from paper_purchase_decision import analyze, main, submit, validate
from paper_opportunity_intelligence import PAPER

NOW = datetime(2026, 11, 7, 20, tzinfo=timezone.utc)  # Saturday
ID = 'hedgeops-manual-123'


class PurchaseDecisionTests(unittest.TestCase):
    def broker(self, host, path, key, secret, *, params=None, payload=None):
        self.assertEqual(host, PAPER)
        if path == '/v2/orders:by_client_order_id':
            raise RuntimeError('Alpaca HTTP 404')
        if path == '/v2/account':
            return {'status': 'ACTIVE', 'trading_blocked': False, 'account_blocked': False,
                    'cash': '1000', 'buying_power': '1000'}
        if path == '/v2/assets/SPY':
            return {'status': 'active', 'tradable': True, 'fractionable': True}
        if path == '/v2/orders':
            self.assertEqual(payload['notional'], '25.00')
            return dict(payload, id='paper-test', status='accepted')
        self.fail(path)  # In particular, there must be no market-open gate.

    def test_weekend_submission_is_allowed_but_not_claimed_filled(self):
        report = submit('SPY', Decimal('25'), ID, key='k', secret='s', get=self.broker)
        self.assertEqual(report['status'], 'BROKER_ACCEPTED_PENDING_FILL')
        self.assertTrue(report['order_submitted'])
        self.assertFalse(report['order_filled'])

    def test_existing_order_reconciles_without_second_post_or_cash_check(self):
        calls = []
        def get(host, path, *a, **kw):
            calls.append(path)
            return {'id': 'paper-test', 'symbol': 'SPY', 'side': 'buy', 'notional': '25',
                    'client_order_id': ID, 'status': 'filled'}
        report = submit('SPY', Decimal('25'), ID, key='k', secret='s', get=get)
        self.assertEqual(calls, ['/v2/orders:by_client_order_id'])
        self.assertEqual(report['status'], 'BROKER_FILLED')
        self.assertTrue(report['reconciled_existing_order'])

    def test_lookup_failure_prevents_post(self):
        calls = []
        def fail(*a, **kw):
            calls.append(kw)
            raise RuntimeError('Alpaca HTTP 500')
        with self.assertRaises(RuntimeError):
            submit('SPY', Decimal('25'), ID, key='k', secret='s', get=fail)
        self.assertEqual(len(calls), 1)
        self.assertNotIn('payload', calls[0])

    def test_id_mismatch_cannot_be_claimed_as_existing_purchase(self):
        def get(*a, **kw):
            return {'id': 'other', 'symbol': 'AAPL', 'side': 'buy', 'notional': '25',
                    'client_order_id': ID, 'status': 'filled'}
        with self.assertRaises(RuntimeError):
            submit('SPY', Decimal('25'), ID, key='k', secret='s', get=get)

    def test_offline_reference_purchase_always_has_analysis_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
            with patch('paper_purchase_decision.request_json', side_effect=AssertionError('No network')):
                code = main(['--symbol', 'SPY', '--notional', '25', '--request-id', ID,
                             '--reference-price', '500', '--thesis', 'Test a fixed holding period',
                             '--output-dir', tmp])
            report = json.loads((Path(tmp)/'decision.json').read_text())
        self.assertEqual(code, 0)
        self.assertEqual(report['status'], 'REFERENCE_SIMULATION_RECORDED')
        self.assertEqual(report['hypothetical_purchase']['quantity'], '0.05')
        self.assertFalse(report['order_filled'])
        self.assertFalse(report['order_submitted'])
        self.assertEqual(report['analysis']['hypothesis'], 'Test a fixed holding period')

    def test_no_price_means_decision_recorded_not_fabricated_fill(self):
        result = analyze('SPY', now=NOW)
        self.assertIsNone(result['reference'])
        self.assertTrue(result['unknowns'])

    def test_stale_weekend_quote_is_labeled_reference_only(self):
        def get(*a, **kw):
            return {'quote': {'t': '2026-11-06T20:00:00Z', 'bp': '499', 'ap': '500'}}
        result = analyze('SPY', key='k', secret='s', now=NOW, get=get,
                         bars_fetch=lambda *a, **kw: {'SPY': []})
        self.assertFalse(result['reference']['is_executable_quote'])
        self.assertGreater(result['reference']['age_seconds'], 120)
        self.assertTrue(any('older' in x for x in result['unknowns']))

    def test_missing_postgres_ledger_blocks_paper_submission(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
             {'ALPACA_API_KEY': 'k', 'ALPACA_API_SECRET': 's'}, clear=True):
            with patch('paper_purchase_decision.analyze', return_value={'reference': None}), \
                 patch('paper_purchase_decision.submit') as submit_call:
                code = main(['--symbol', 'SPY', '--notional', '25', '--request-id', ID,
                             '--submit-paper', '--output-dir', tmp])
            report = json.loads((Path(tmp)/'decision.json').read_text())
        self.assertEqual(code, 1)
        submit_call.assert_not_called()
        self.assertEqual(report['status'], 'BROKER_UNCONFIRMED_REQUIRES_RECONCILIATION')
        self.assertIn('analysis', report)

    def test_insufficient_cash_never_posts(self):
        def get(host, path, *a, **kw):
            if path == '/v2/account':
                return {'status': 'ACTIVE', 'trading_blocked': False, 'account_blocked': False,
                        'cash': '1', 'buying_power': '1'}
            return self.broker(host, path, *a, **kw)
        with self.assertRaisesRegex(ValueError, 'Insufficient'):
            submit('SPY', Decimal('25'), ID, key='k', secret='s', get=get)

    def test_missing_keys_cannot_submit(self):
        with self.assertRaises(ValueError):
            submit('SPY', Decimal('25'), ID, key='', secret='',
                   get=lambda *a, **k: self.fail('No broker access'))

    def test_invalid_values_fail_before_network(self):
        for amount in ['0', '201', 'NaN', 'Infinity', '1.001']:
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                validate('SPY', amount, ID)
        for symbol in ['spy', '../SPY', 'SPY;id', '']:
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                validate(symbol, '25', ID)

    def test_reconcile_only_cannot_post(self):
        order = {'id': 'paper-test', 'symbol': 'SPY', 'side': 'buy', 'notional': '25',
                 'client_order_id': ID, 'status': 'accepted'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,
             {'ALPACA_API_KEY': 'k', 'ALPACA_API_SECRET': 's'}, clear=True):
            with patch('paper_purchase_decision.analyze', return_value={'reference': None}), \
                 patch('paper_purchase_decision.request_json', return_value=order) as call:
                self.assertEqual(main(['--symbol', 'SPY', '--notional', '25', '--request-id', ID,
                                       '--reconcile-only', '--output-dir', tmp]), 0)
            self.assertEqual(call.call_args.args[1], '/v2/orders:by_client_order_id')
            self.assertNotIn('payload', call.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
