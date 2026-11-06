import unittest
from unittest.mock import patch
from paper_broker_reconciliation import order_key, reconcile_symbol, fetch_broker_state

class BrokerSafetyTests(unittest.TestCase):
    def test_stable_order_identity(self):
        self.assertEqual(order_key("trend-v1", "SPY", "2026-11-06", 25), order_key("trend-v1", "SPY", "2026-11-06", 25.0))
    def test_different_sessions_differ(self):
        self.assertNotEqual(order_key("trend-v1", "SPY", "2026-11-06", 25), order_key("trend-v1", "SPY", "2026-11-07", 25))
    def test_duplicate_order(self):
        cid = order_key("trend-v1", "SPY", "2026-11-06", 25)
        self.assertEqual(reconcile_symbol("SPY", cid, [], [{"symbol": "SPY", "client_order_id": cid, "status": "filled"}]), "DUPLICATE_ORDER")
    def test_existing_position(self):
        self.assertEqual(reconcile_symbol("SPY", "id", [{"symbol": "SPY"}], []), "EXISTING_POSITION")
    def test_open_order(self):
        self.assertEqual(reconcile_symbol("SPY", "id", [], [{"symbol": "SPY", "status": "new"}]), "OPEN_ORDER")
    @patch("paper_broker_reconciliation.request")
    def test_closed_market_fails(self, api):
        api.side_effect = [{"status": "ACTIVE"}, [], [], {"is_open": False}]
        with self.assertRaises(ValueError):
            fetch_broker_state("key", "secret")

if __name__ == "__main__":
    unittest.main()
