"""Offline regression tests for read-only position loss monitoring."""
import pytest
from unittest.mock import patch
from position_loss_monitor import evaluate_positions, monitor, notify_webhook, validate_thresholds


def position(symbol="SPY", market="90", pl="-10"):
    return {"symbol": symbol, "qty": "1", "cost_basis": "100",
            "market_value": market, "unrealized_pl": pl}


def test_severity_boundaries():
    result = evaluate_positions([position("SPY", "95", "-5"),
                                 position("QQQ", "90", "-10"),
                                 position("VTI", "99", "-1")])
    assert {p["symbol"]: p["severity"] for p in result} == {
        "SPY": "warning", "QQQ": "critical", "VTI": "ok"}
    assert result[0]["recommended_action"].startswith("REVIEW_POSITION")


def test_no_positions():
    assert evaluate_positions([]) == []


@pytest.mark.parametrize("positions", [
    {}, [None], [{"symbol": "SPY"}], [position(pl="-20")],
    [position(market="NaN", pl="-10")], [position(market="-1", pl="-101")],
    [position(market="90", pl="Infinity")],
])
def test_bad_broker_data_fails_closed(positions):
    with pytest.raises(ValueError):
        evaluate_positions(positions)


@pytest.mark.parametrize("warning,critical", [
    (0, 10), (10, 10), (20, 10), (-1, 10),
    (5, float("nan")), (5, 101), (True, 10),
])
def test_invalid_thresholds(warning, critical):
    with pytest.raises(ValueError):
        validate_thresholds(warning, critical)


def test_monitor_only_reads_positions():
    with patch("position_loss_monitor._get_json", return_value=[position()]) as get:
        result = monitor(mode="paper", key="test-key", secret="test-secret")
    get.assert_called_once_with("https://paper-api.alpaca.markets", "/v2/positions",
                                "test-key", "test-secret")
    assert result["order_submission_enabled"] is False
    assert result["critical_count"] == 1


def test_live_monitor_still_only_reads():
    with patch("position_loss_monitor._get_json", return_value=[]) as get:
        monitor(mode="live", key="key", secret="secret")
    assert get.call_args.args[0] == "https://api.alpaca.markets"
    assert get.call_args.args[1] == "/v2/positions"


def test_notification_opt_in_and_no_alerts():
    with patch("position_loss_monitor.urlopen") as call:
        assert notify_webhook({"positions": [dict(severity="ok")]}, "") is False
        assert notify_webhook({"positions": [dict(severity="ok")]}, "https://example.com/hook") is False
        call.assert_not_called()


@pytest.mark.parametrize("url", ["http://example.com/hook", "file:///tmp/a",
                                 "https://user:pass@example.com/hook"])
def test_insecure_webhook_rejected(url):
    with pytest.raises(ValueError):
        notify_webhook({"positions": [dict(severity="critical")]}, url)
