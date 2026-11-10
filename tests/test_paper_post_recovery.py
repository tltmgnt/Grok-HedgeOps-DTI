"""No-network tests for broker-authoritative recovery after ambiguous paper POST."""
from decimal import Decimal
import unittest

from paper_purchase_decision import submit

RID = 'hedgeops-recovery-123'


class RecoveryTests(unittest.TestCase):
    def _broker(self, *, recover):
        calls = []
        lookups = 0

        def get(host, path, key, secret, *, params=None, payload=None):
            nonlocal lookups
            calls.append((path, payload))
            if path == '/v2/orders:by_client_order_id':
                lookups += 1
                if lookups == 1:
                    raise RuntimeError('Alpaca HTTP 404')
                if recover:
                    return {'id': 'accepted-123', 'symbol': 'SPY', 'side': 'buy',
                            'notional': '25', 'client_order_id': RID, 'status': 'accepted'}
                raise RuntimeError('Alpaca HTTP 404')
            if path == '/v2/account':
                return {'status': 'ACTIVE', 'trading_blocked': False,
                        'account_blocked': False, 'cash': '100', 'buying_power': '100'}
            if path == '/v2/assets/SPY':
                return {'status': 'active', 'tradable': True, 'fractionable': True}
            if path == '/v2/orders':
                raise RuntimeError('POST timed out')
            self.fail(path)

        return get, calls

    def test_ambiguous_post_reconciles_confirmed_order(self):
        get, calls = self._broker(recover=True)
        result = submit('SPY', Decimal('25'), RID, key='k', secret='s', get=get)
        self.assertEqual(result['status'], 'BROKER_ACCEPTED_PENDING_FILL')
        self.assertTrue(result['reconciled_existing_order'])
        self.assertEqual(sum(path == '/v2/orders' for path, _ in calls), 1)
        self.assertEqual(sum(path == '/v2/orders:by_client_order_id' for path, _ in calls), 2)

    def test_ambiguous_post_without_confirmation_stays_uncertain(self):
        get, calls = self._broker(recover=False)
        with self.assertRaisesRegex(RuntimeError, 'outcome uncertain'):
            submit('SPY', Decimal('25'), RID, key='k', secret='s', get=get)
        self.assertEqual(sum(path == '/v2/orders' for path, _ in calls), 1)

    def test_mismatched_recovery_acknowledgment_rejected(self):
        get, calls = self._broker(recover=True)

        def mismatch(*args, **kwargs):
            result = get(*args, **kwargs)
            if isinstance(result, dict) and result.get('id') == 'accepted-123':
                result['symbol'] = 'AAPL'
            return result

        with self.assertRaisesRegex(RuntimeError, 'Ambiguous broker acknowledgment'):
            submit('SPY', Decimal('25'), RID, key='k', secret='s', get=mismatch)
        self.assertEqual(sum(path == '/v2/orders' for path, _ in calls), 1)


if __name__ == '__main__':
    unittest.main()
