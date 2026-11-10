"""Synthetic fixtures only; no external providers or real account observations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from investment_research import (CHECKS, build_report, collect_quotes, evaluate, main,
                                 number, save_report, validate)

NOW = datetime(2026, 11, 10, 19, 35, tzinfo=timezone.utc)
POLICY = Path(__file__).resolve().parents[1] / 'research/investment_policy.json'


def policy():
    return json.loads(POLICY.read_text())


def reviewed_policy():
    p = policy()
    for row in p['candidates']:
        row['eps_basis'] = 'reviewed_annual'
        row['review'].update(reviewed_at=NOW.isoformat(), financials_as_of=NOW.isoformat(),
                             **dict.fromkeys(CHECKS, True))
    return p


def quote(price='500', **overrides):
    q = {'timestamp': (NOW-timedelta(seconds=10)).isoformat(), 'bid': price,
         'ask': price, 'feed': 'iex', 'coverage': 'single_exchange'}
    q.update(overrides)
    return q


class ResearchTests(unittest.TestCase):
    def test_workbook_inputs_never_ready_even_at_cheap_price(self):
        p = policy()
        r = build_report(p, {'MSFT': quote(), 'GOOGL': quote('180')}, now=NOW, origin='SYNTHETIC_TEST')
        self.assertEqual(len(r['assessments']), 4)
        self.assertFalse(r['order_authority'])
        for x in r['assessments']:
            self.assertNotEqual(x['status'], 'REVIEW_READY')
            self.assertIn('ILLUSTRATIVE_EPS_NOT_EXECUTABLE', x['failed_gates'])

    def test_base_case_math_and_horizon_prices(self):
        p = reviewed_policy()
        row = p['candidates'][0]
        two = evaluate(row, '1-2y', quote(), now=NOW)
        five = evaluate(row, '5y', quote(), now=NOW)
        self.assertEqual(two['scenario_values']['base'], '662.47')
        self.assertEqual(two['status'], 'REVIEW_READY')
        self.assertEqual(five['status'], 'WATCH')
        self.assertAlmostEqual(float(two['entry_ceiling']), 528.12)
        self.assertAlmostEqual(float(five['entry_ceiling']), 489)

    def test_stale_future_missing_crossed_and_wide_quotes_block(self):
        row = reviewed_policy()['candidates'][0]
        for q in (None, {}, quote(timestamp=(NOW-timedelta(seconds=121)).isoformat()),
                  quote(timestamp=(NOW+timedelta(seconds=1)).isoformat()),
                  quote(bid='501'), quote(ask='510'), quote(ask=True),
                  quote(timestamp='2026-11-10T19:35:00')):
            with self.subTest(q=q):
                r = evaluate(row, '1-2y', q, now=NOW)
                self.assertIn('CURRENT_QUOTE_REQUIRED', r['failed_gates'])

    def test_ask_and_lower_zone_used_not_midpoint_or_falling_price(self):
        row = reviewed_policy()['candidates'][0]
        for q in [quote('479'), quote('519', ask='521')]:
            self.assertIn('PRICE_OUTSIDE_ENTRY_ZONE', evaluate(row, '1-2y', q, now=NOW)['failed_gates'])

    def test_every_financial_check_must_be_boolean_true(self):
        for check in CHECKS:
            for value in (False, None, 'true', 1):
                row = reviewed_policy()['candidates'][0]
                row['review'][check] = value
                r = evaluate(row, '1-2y', quote(), now=NOW)
                self.assertIn(check.upper()+'_REQUIRED', r['failed_gates'])

    def test_stale_future_or_undated_review_blocks(self):
        for stamp in [None, (NOW-timedelta(days=91)).isoformat(), (NOW+timedelta(days=1)).isoformat()]:
            row = reviewed_policy()['candidates'][0]
            row['review']['reviewed_at'] = stamp
            self.assertNotEqual(evaluate(row, '1-2y', quote(), now=NOW)['status'], 'REVIEW_READY')

    def test_invalid_policy_and_numbers(self):
        for value in [True, 'NaN', 'Infinity', '-1']:
            with self.assertRaises(ValueError): number(value)
        p = policy();p['candidates'].append(deepcopy(p['candidates'][0]))
        with self.assertRaises(ValueError): validate(p)
        p = policy();p['candidates'][0]['symbol'] = '../orders'
        with self.assertRaises(ValueError): validate(p)

    def test_missing_credentials_never_contacts_provider(self):
        self.assertEqual(collect_quotes(policy(), key='', secret='', get=lambda *a, **k: self.fail('network')),
                         ({}, ['MARKET_DATA_NOT_CONFIGURED']))

    def test_provider_errors_sanitized_and_quote_only(self):
        def get(host, path, key, secret, **kw):
            self.assertEqual(host, 'https://data.alpaca.markets')
            self.assertTrue(path.endswith('/quotes/latest'))
            self.assertNotIn('payload', kw)
            raise RuntimeError('sensitive-provider-response')
        qs, errors = collect_quotes(policy(), key='fixture', secret='fixture', get=get)
        self.assertEqual(qs, {})
        self.assertNotIn('sensitive', str(errors))

    def test_cli_missing_credentials_persists_failure_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict('os.environ', {}, clear=True):
            self.assertEqual(main(['--policy', str(POLICY), '--output', tmp]), 1)
            report = json.loads((Path(tmp)/'research.json').read_text())
            self.assertEqual(report['data_errors'], ['MARKET_DATA_NOT_CONFIGURED'])
            self.assertTrue((Path(tmp)/'summary.md').exists())
