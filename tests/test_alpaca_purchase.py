"""Offline tests for live order safeguards; broker API is mocked."""
import pytest
from unittest.mock import patch
from alpaca_purchase import purchase_alpaca, CONFIRMATION


def broker_response(base, path, key, secret, *, payload=None):
    if path == "/v2/account":
        return {"status": "ACTIVE", "trading_blocked": False,
                "account_blocked": False, "buying_power": "100", "cash": "100"}
    if path == "/v2/assets/SPY":
        return {"status": "active", "tradable": True, "fractionable": True}
    if path == "/v2/orders":
        assert payload["side"] == "buy"
        assert payload["notional"] == "25.00"
        return {"id": "synthetic-id", "status": "accepted"}
    raise AssertionError(path)


def test_live_requires_explicit_confirmation_and_makes_no_request():
    with patch("alpaca_purchase._request") as call:
        with pytest.raises(PermissionError):
            purchase_alpaca("SPY", 25, mode="live", key="key", secret="secret",
                            request_id="hedgeops-12345678")
        call.assert_not_called()


@pytest.mark.parametrize("notional", [0, -1, 201, float("nan"), float("inf"), True])
def test_invalid_amounts_fail_before_network(notional):
    with patch("alpaca_purchase._request") as call:
        with pytest.raises(ValueError):
            purchase_alpaca("SPY", notional, mode="paper", key="key", secret="secret",
                            request_id="hedgeops-12345678")
        call.assert_not_called()


def test_live_order_is_submitted_only_after_all_checks():
    with patch("alpaca_purchase._request", side_effect=broker_response) as call:
        result = purchase_alpaca("SPY", 25, mode="live", confirmation=CONFIRMATION,
                                 key="key", secret="secret", request_id="hedgeops-12345678")
    assert call.call_count == 3
    assert result["order_submitted"] is True
    assert result["order_filled"] is False
    assert result["mode"] == "live"


def test_account_insufficient_cash_blocks_order():
    def insufficient(base, path, key, secret, *, payload=None):
        if path == "/v2/account":
            return {"status": "ACTIVE", "trading_blocked": False,
                    "account_blocked": False, "buying_power": "20", "cash": "20"}
        raise AssertionError("should never request asset or submit order")
    with patch("alpaca_purchase._request", side_effect=insufficient) as call:
        with pytest.raises(PermissionError):
            purchase_alpaca("SPY", 25, mode="paper", key="key", secret="secret",
                            request_id="hedgeops-12345678")
    assert call.call_count == 1


def test_live_paper_endpoints_are_distinct():
    bases = []
    def record(base, path, key, secret, *, payload=None):
        bases.append(base)
        return broker_response(base, path, key, secret, payload=payload)
    with patch("alpaca_purchase._request", side_effect=record):
        purchase_alpaca("SPY", 25, mode="paper", key="key", secret="secret",
                        request_id="hedgeops-12345678")
    assert set(bases) == {"https://paper-api.alpaca.markets"}
