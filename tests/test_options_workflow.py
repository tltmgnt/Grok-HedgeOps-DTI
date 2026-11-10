"""Offline options workflow safety tests; never contacts a broker."""
import unittest
from datetime import date, timedelta

from options_workflow import plan, verify_standard_contract

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

    def test_contract_metadata_match_is_offline_and_not_broker_authenticated(self):
        p = options('buy_call')
        contract = {'underlying_symbol': 'SPY', 'expiration_date': EXPIRY,
                    'type': 'call', 'strike_price': '500.00',
                    'multiplier': '100', 'symbol': 'SPY   ' + EXPIRY[2:4] + EXPIRY[5:7] + EXPIRY[8:10] + 'C00500000'}
        result = verify_standard_contract(p, contract)
        self.assertTrue(result['contract_matches_plan'])
        self.assertFalse(result['broker_source_authenticated'])
        self.assertFalse(result['broker_order_submitted'])

    def test_short_option_contract_matching_requires_trusted_evidence(self):
        yymmdd = EXPIRY[2:4] + EXPIRY[5:7] + EXPIRY[8:10]
        for action, extra, right in (
            ('covered_call', {'position_verified': True}, 'C'),
            ('cash_secured_put', {'collateral_verified': True}, 'P'),
        ):
            with self.subTest(action=action):
                p = options(action, **extra)
                contract = {'underlying_symbol': 'SPY', 'expiration_date': EXPIRY,
                            'type': 'call' if right == 'C' else 'put',
                            'strike_price': '500.00', 'multiplier': '100',
                            'symbol': 'SPY   ' + yymmdd + right + '00500000'}
                with self.assertRaisesRegex(ValueError, 'trusted collateral or position'):
                    verify_standard_contract(p, contract)

    def test_contract_matcher_rejects_removed_or_modified_warnings(self):
        p = options('buy_call')
        yymmdd = EXPIRY[2:4] + EXPIRY[5:7] + EXPIRY[8:10]
        contract = {'underlying_symbol': 'SPY', 'expiration_date': EXPIRY,
                    'type': 'call', 'strike_price': '500.00',
                    'multiplier': '100', 'symbol': 'SPY   ' + yymmdd + 'C00500000'}
        for altered in (
            {k: v for k, v in p.items() if k != 'warning'},
            {**p, 'warning': ''},
            {**p, 'contract_warning': ''},
            {**p, 'unexpected_execution_approval': True},
        ):
            with self.subTest(fields=tuple(altered)):
                with self.assertRaises(ValueError):
                    verify_standard_contract(altered, contract)

    def test_contract_verification_rejects_tampered_plan_fields(self):
        p = options('buy_call')
        yymmdd = EXPIRY[2:4] + EXPIRY[5:7] + EXPIRY[8:10]
        contract = {'underlying_symbol': 'SPY', 'expiration_date': EXPIRY,
                    'type': 'call', 'strike_price': '500.00',
                    'multiplier': '100', 'symbol': 'SPY   ' + yymmdd + 'C00500000'}
        for field, value in (
            ('contracts', 99), ('limit_price', '0.01'),
            ('estimated_premium_usd', '0.01'),
            ('estimated_max_loss_usd', '0.01'),
            ('assumed_contract_multiplier', 1),
            ('risk_estimates_are_broker_verified', True),
            ('contract_terms_verified', True),
            ('broker_order_submitted', True),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'tampered'):
                    verify_standard_contract({**p, field: value}, contract)
        self.assertTrue(verify_standard_contract(p, contract)['contract_matches_plan'])

    def test_option_symbol_must_match_metadata_and_plan(self):
        p = options('buy_call')
        yymmdd = EXPIRY[2:4] + EXPIRY[5:7] + EXPIRY[8:10]
        base = {'underlying_symbol': 'SPY', 'expiration_date': EXPIRY,
                'type': 'call', 'strike_price': '500.00', 'multiplier': '100'}
        for symbol in ('AAPL  ' + yymmdd + 'C00500000',
                       'SPY   270101C00500000' if yymmdd != '270101'
                       else 'SPY   280101C00500000',
                       'SPY   ' + yymmdd + 'P00500000',
                       'SPY   ' + yymmdd + 'C00501000'):
            with self.subTest(symbol=symbol):
                with self.assertRaisesRegex(ValueError, 'conflicts'):
                    verify_standard_contract(p, {**base, 'symbol': symbol})

    def test_contract_metadata_mismatch_or_adjustment_fails_closed(self):
        p = options('buy_put')
        contract = {'underlying_symbol': 'SPY', 'expiration_date': EXPIRY,
                    'type': 'put', 'strike_price': '500.00',
                    'multiplier': '100', 'symbol': 'SPY   ' + EXPIRY[2:4] + EXPIRY[5:7] + EXPIRY[8:10] + 'P00500000'}
        for field, invalid in (
            ('underlying_symbol', 'AAPL'), ('expiration_date', '2030-01-01'),
            ('type', 'call'), ('strike_price', '501.00'),
            ('multiplier', '10'), ('multiplier', 'NaN'),
            ('symbol', ''),
        ):
            with self.subTest(field=field, invalid=invalid):
                with self.assertRaises(ValueError):
                    verify_standard_contract(p, {**contract, field: invalid})
        with self.assertRaises(ValueError):
            verify_standard_contract(p, {})

    def test_contract_multiplier_is_explicitly_unverified(self):
        for action, extra in (
            ('buy_call', {}),
            ('cash_secured_put', {'collateral_verified': True}),
            ('covered_call', {'position_verified': True}),
        ):
            with self.subTest(action=action):
                result = options(action, **extra)
                self.assertEqual(result['assumed_contract_multiplier'], 100)
                self.assertFalse(result['contract_terms_verified'])
                self.assertIn('Adjusted', result['contract_warning'])
                self.assertFalse(result['broker_order_submitted'])

    def test_long_options_premium_is_maximum_planned_loss(self):
        for action in ('buy_call', 'buy_put'):
            result = options(action, contracts=3, limit_price='1.25')
            self.assertEqual(result['estimated_premium_usd'], '375.00')
            self.assertEqual(result['estimated_max_loss_usd'], '375.00')
            self.assertFalse(result['risk_estimates_are_broker_verified'])

    def test_short_put_displays_gross_assignment_collateral(self):
        result = options('cash_secured_put', contracts=2, strike='500.00',
                         limit_price='2.50', collateral_verified=True)
        self.assertEqual(result['estimated_premium_usd'], '500.00')
        self.assertEqual(result['cash_secured_put_collateral_usd'], '100000.00')
        self.assertEqual(result['estimated_max_loss_usd'], '100000.00')
        self.assertFalse(result['broker_order_submitted'])

    def test_covered_call_displays_share_requirement_without_false_loss_cap(self):
        result = options('covered_call', contracts=2, position_verified=True)
        self.assertEqual(result['covered_call_shares_required'], 200)
        self.assertIsNone(result['estimated_max_loss_usd'])
        self.assertFalse(result['risk_estimates_are_broker_verified'])

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

    def test_expiration_horizon_rejects_century_alias_and_distant_dates(self):
        today = date.today()
        for expiry in (today.replace(year=today.year + 100).isoformat(),
                       today.replace(year=today.year + 6).isoformat()):
            with self.subTest(expiry=expiry):
                with self.assertRaisesRegex(ValueError, 'five-year'):
                    options(expiration=expiry)
        self.assertEqual(options(expiration=EXPIRY)['expiration'], EXPIRY)

    def test_ambiguous_expiration_formats_fail_closed(self):
        for expiry in ('20300101', '2030-1-01', '2030-01-1', '2030-W01-1'):
            with self.subTest(expiry=expiry):
                with self.assertRaisesRegex(ValueError, 'YYYY-MM-DD'):
                    options(expiration=expiry)

    def test_unbounded_strike_and_premium_fail_closed(self):
        for field in ('strike', 'limit_price'):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'planner safety bound'):
                    options(**{field: '1000000.01'})

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
