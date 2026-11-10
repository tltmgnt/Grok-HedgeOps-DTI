"""Offline options workflow safety tests; never contacts a broker."""
import unittest
from datetime import date, timedelta

from options_workflow import plan

EXPIRY = (date.today() + timedelta(days=90)).isoformat()


def options(action='buy_call', mode='simulate', **overrides):
    params = dict(action=action, mode=mode, symbol='SPY', expiration=EXPIRY,
                  strike='500.00', contracts=1, limit_price='2.50')
    params.update(overrides)
    return plan(**params)


class OptionsWorkflowTests(unittest.TestCase):
    def test_long_calls_and_puts_are_plan_only_in_all_modes(self):
        for action in ('buy_call', 'buy_put'):
            for mode in ('simulate', 'paper', 'live'):
                with self.subTest(action=action, mode=mode):
                    kwargs = {'approval': 'I_APPROVE_LIVE_OPTIONS'} if mode == 'live' else {}
                    result = options(action, mode, **kwargs)
                    self.assertEqual(result['status'], 'VALIDATED_PLAN_ONLY')
                    self.assertFalse(result['broker_order_submitted'])
                    self.assertEqual(result['estimated_premium_usd'], '250.00')

    def test_live_requires_explicit_approval_phrase(self):
        for approval in ('', 'yes', 'I_APPROVE_PAPER_OPTIONS'):
            with self.subTest(approval=approval):
                with self.assertRaisesRegex(ValueError, 'explicit approval'):
                    options(mode='live', approval=approval)

    def test_short_calls_fail_closed_without_covered_shares(self):
        for action in ('sell_call', 'covered_call'):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, 'verified covered shares'):
                    options(action)
                result = options(action, position_verified=True)
                self.assertFalse(result['broker_order_submitted'])

    def test_short_puts_fail_closed_without_cash_collateral(self):
        for action in ('sell_put', 'cash_secured_put'):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, 'verified cash collateral'):
                    options(action)
                result = options(action, collateral_verified=True)
                self.assertFalse(result['broker_order_submitted'])

    def test_lifecycle_actions_are_not_executable(self):
        for action in ('close', 'roll', 'reconcile'):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, 'verified existing'):
                    options(action)

    def test_invalid_expiry_and_nonfinite_price_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'Expired contract'):
            options(expiration=(date.today() - timedelta(days=1)).isoformat())
        for value in ('NaN', 'Infinity', '-1', '0', '1.001'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    options(limit_price=value)

    def test_invalid_contracts_and_symbols_fail_closed(self):
        for count in (0, -1, 101, True, 1.5):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    options(contracts=count)
        for symbol in ('spy', 'SPY; echo unsafe', ''):
            with self.subTest(symbol=symbol):
                with self.assertRaises(ValueError):
                    options(symbol=symbol)


if __name__ == '__main__':
    unittest.main()
