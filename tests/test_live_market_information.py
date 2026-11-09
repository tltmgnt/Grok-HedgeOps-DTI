"""Offline provider fixtures; no broker orders or network calls."""
from datetime import timedelta
import os
import unittest
from unittest.mock import patch
from tests.test_paper_opportunity_intelligence import NOW, broker
from paper_opportunity_intelligence import news_evidence
from live_market_information import snapshot


class LiveInformationTests(unittest.TestCase):
    def provider(self, host, path, key, secret, **kwargs):
        self.assertIsNone(kwargs.get('payload'))
        if path.endswith('/quotes/latest'):
            return {'quote': {'t': (NOW - timedelta(seconds=10)).isoformat(), 'bp': 100, 'ap': 100.1}}
        return broker(host, path, key, secret, **kwargs)

    def test_current_snapshot_records_feed_and_age_without_orders(self):
        with patch.dict(os.environ, {'PAPER_DATA_FEED': 'iex'}):
            result = snapshot('HD', key='test', secret='test', get=self.provider, clock=lambda: NOW)
        self.assertEqual(result['status'], 'CURRENT')
        self.assertFalse(result['order_authority'])
        self.assertEqual(result['quote']['age_seconds'], 10)
        self.assertEqual(result['quote']['coverage'], 'single_exchange')

    def test_stale_quote_never_published_as_current(self):
        def get(*args, **kwargs):
            if args[1].endswith('/quotes/latest'):
                return {'quote': {'t': (NOW - timedelta(minutes=3)).isoformat(), 'bp': 100, 'ap': 100.1}}
            return self.provider(*args, **kwargs)
        result = snapshot('HD', key='test', secret='test', get=get, clock=lambda: NOW)
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertIsNone(result['quote'])

    def test_closed_market_is_explicit(self):
        def get(*args, **kwargs):
            if args[1] == '/v2/clock':
                return {'is_open': False}
            return self.provider(*args, **kwargs)
        result = snapshot('HD', key='test', secret='test', get=get, clock=lambda: NOW)
        self.assertEqual(result['status'], 'MARKET_CLOSED')

    def test_news_rejects_stale_future_naive_and_missing_timestamps(self):
        for stamp in ['', None, 'invalid', '2026-11-04T16:00:00',
                      (NOW - timedelta(days=8)).isoformat(), (NOW + timedelta(seconds=1)).isoformat()]:
            with self.subTest(stamp=stamp):
                def get(*args, **kwargs):
                    return {'news': [{'symbols': ['HD'], 'headline': 'Earnings results', 'created_at': stamp}]}
                self.assertEqual(news_evidence('HD', 'test', 'test', now=NOW, get=get), [])

    def test_invalid_input_does_not_call_provider(self):
        for symbol, key in [('HD/../../orders', 'test'), ('HD', '')]:
            with self.assertRaises(ValueError):
                snapshot(symbol, key=key, secret='test', get=lambda *a, **k: self.fail('Network'))
