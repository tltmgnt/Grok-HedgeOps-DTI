"""Regression tests for Alpaca client-order-ID preflight (no network)."""
import unittest
from unittest.mock import patch

import alpaca_purchase


class PreflightTests(unittest.TestCase):
    def _call(self):
        return alpaca_purchase.purchase_alpaca(
            "SPY", 10, mode="paper", key="fake", secret="fake",
            request_id="stable_request_123",
        )

    def test_existing_order_blocks_post(self):
        calls = []

        def fake_request(base, path, key, secret, *, payload=None, allow_not_found=False):
            calls.append((path, payload))
            if path == "/v2/account":
                return {"status": "ACTIVE", "trading_blocked": False,
                        "account_blocked": False, "cash": "100", "buying_power": "100"}
            if path == "/v2/assets/SPY":
                return {"status": "active", "tradable": True, "fractionable": True}
            if path.startswith("/v2/orders:by_client_order_id?"):
                return {"id": "existing", "status": "filled"}
            self.fail("Order POST must never occur when ID already exists")

        with patch.object(alpaca_purchase, "_request", side_effect=fake_request):
            with self.assertRaisesRegex(PermissionError, "already exists"):
                self._call()
        self.assertEqual(len(calls), 3)

    def test_lookup_error_blocks_post(self):
        def fake_request(base, path, key, secret, *, payload=None, allow_not_found=False):
            if path == "/v2/account":
                return {"status": "ACTIVE", "trading_blocked": False,
                        "account_blocked": False, "cash": "100", "buying_power": "100"}
            if path == "/v2/assets/SPY":
                return {"status": "active", "tradable": True, "fractionable": True}
            raise RuntimeError("Broker lookup unavailable")

        with patch.object(alpaca_purchase, "_request", side_effect=fake_request):
            with self.assertRaisesRegex(RuntimeError, "lookup unavailable"):
                self._call()

    def test_missing_order_allows_single_post(self):
        posts = []

        def fake_request(base, path, key, secret, *, payload=None, allow_not_found=False):
            if path == "/v2/account":
                return {"status": "ACTIVE", "trading_blocked": False,
                        "account_blocked": False, "cash": "100", "buying_power": "100"}
            if path == "/v2/assets/SPY":
                return {"status": "active", "tradable": True, "fractionable": True}
            if path.startswith("/v2/orders:by_client_order_id?"):
                self.assertTrue(allow_not_found)
                return None
            if path == "/v2/orders":
                posts.append(payload)
                return {"id": "new-order", "status": "accepted"}
            self.fail("Unexpected request")

        with patch.object(alpaca_purchase, "_request", side_effect=fake_request):
            result = self._call()
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["client_order_id"], "stable_request_123")
        self.assertFalse(result["order_filled"])


if __name__ == "__main__":
    unittest.main()
