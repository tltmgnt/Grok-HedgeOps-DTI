"""Safety regression tests for non-executable live options gate."""
import os
import unittest
from unittest.mock import patch

from options_execution_gate import evaluate_execution_gate

BASE = dict(environment='live', broker_authenticated=True,
            account_verified=True, ledger_reserved=True,
            reconciliation_healthy=True, kill_switch_clear=True,
            risk_limits_verified=True,
            operator_approval='independent-operator-approval-12345',
            expected_approval='independent-operator-approval-12345',
            order_notional_usd='250.00', max_order_notional_usd='500.00')


class ExecutionGateTests(unittest.TestCase):
    def evaluate(self, **overrides):
        return evaluate_execution_gate(**{**BASE, **overrides})

    def test_default_live_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            decision = self.evaluate()
        self.assertFalse(decision.permitted)
        self.assertIn('disabled', decision.reason)

    def test_enabled_flag_is_not_sufficient(self):
        with patch.dict(os.environ, {'OPTIONS_LIVE_EXECUTION_ENABLED': 'true'}):
            decision = self.evaluate()
        self.assertFalse(decision.permitted)
        self.assertIn('adapter', decision.reason)

    def test_missing_safety_checks_fail_closed(self):
        with patch.dict(os.environ, {'OPTIONS_LIVE_EXECUTION_ENABLED': 'true'}):
            for field in ('broker_authenticated', 'account_verified',
                          'ledger_reserved', 'reconciliation_healthy',
                          'kill_switch_clear', 'risk_limits_verified'):
                with self.subTest(field=field):
                    self.assertFalse(self.evaluate(**{field: False}).permitted)
                    self.assertFalse(self.evaluate(**{field: 1}).permitted)

    def test_approval_and_notional_are_required(self):
        with patch.dict(os.environ, {'OPTIONS_LIVE_EXECUTION_ENABLED': 'true'}):
            for changed in ({'operator_approval': 'wrong'},
                            {'expected_approval': ''},
                            {'order_notional_usd': '501.00'},
                            {'order_notional_usd': 'NaN'},
                            {'order_notional_usd': '-1'},
                            {'max_order_notional_usd': '0'}):
                with self.subTest(changed=changed):
                    self.assertFalse(self.evaluate(**changed).permitted)

    def test_paper_is_not_implicitly_executable(self):
        self.assertFalse(self.evaluate(environment='paper').permitted)


if __name__ == '__main__':
    unittest.main()
