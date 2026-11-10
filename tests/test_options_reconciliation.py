"""Offline reconciliation checks: no network, broker auth, or database writes."""
import unittest
from options_reconciliation import assess_snapshot

INTENT = dict(client_order_id='order-1', account_id='acct', environment='paper',
              contract_symbol='SPY   271119C00500000', side='buy',
              quantity=1, status='submission_unknown', broker_order_id=None)
SNAPSHOT = {**{k: INTENT[k] for k in
               ('client_order_id', 'account_id', 'environment',
                'contract_symbol', 'side', 'quantity')},
            'broker_order_id': 'broker-1', 'status': 'filled'}


class ReconciliationTests(unittest.TestCase):
    def test_missing_order_is_never_rejection_proof(self):
        result = assess_snapshot(INTENT, {})
        self.assertEqual(result['status'], 'UNRESOLVED')
        self.assertFalse(result['database_write_authorized'])

    def test_terminal_status_still_requires_authenticated_review(self):
        for status in ('filled', 'cancelled', 'rejected', 'accepted',
                       'partially_filled', 'pending_cancel'):
            with self.subTest(status=status):
                result = assess_snapshot(INTENT, {**SNAPSHOT, 'status': status})
                self.assertEqual(result['status'], 'REVIEW_REQUIRED')
                self.assertFalse(result['database_write_authorized'])

    def test_identity_mismatch_fails_closed(self):
        for key, wrong in (('client_order_id', 'other'),
                           ('account_id', 'other'),
                           ('environment', 'live'),
                           ('contract_symbol', 'AAPL  271119C00500000'),
                           ('side', 'sell'), ('quantity', 2)):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'identity mismatch'):
                    assess_snapshot(INTENT, {**SNAPSHOT, key: wrong})

    def test_conflicting_broker_order_id_rejected(self):
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            assess_snapshot({**INTENT, 'broker_order_id': 'existing'}, SNAPSHOT)

    def test_invalid_broker_id_rejected(self):
        for value in (None, '', 'bad id', 123):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'broker order ID'):
                    assess_snapshot(INTENT, {**SNAPSHOT, 'broker_order_id': value})

    def test_unknown_status_stays_unresolved(self):
        result = assess_snapshot(INTENT, {**SNAPSHOT, 'status': 'mystery'})
        self.assertEqual(result['status'], 'UNRESOLVED')
        self.assertFalse(result['database_write_authorized'])

    def test_non_ambiguous_intent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            assess_snapshot({**INTENT, 'status': 'filled'}, SNAPSHOT)


if __name__ == '__main__':
    unittest.main()
