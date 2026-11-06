"""Tests for historical market-data simulation (no external API calls)."""
from datetime import datetime, timedelta, timezone
import pytest
from historical_market_performance import run

NOW = datetime(2026, 11, 6, tzinfo=timezone.utc)

def mock_fetch(symbols, key, secret, *, now=None):
    assert symbols == ["SPY"]
    return {"SPY": [
        {"t": (NOW - timedelta(days=65-i)).isoformat(), "c": 100.0 + i}
        for i in range(60)
    ]}

def test_real_market_adapter_simulates_without_orders():
    result = run("SPY", "dummy", "dummy", now=NOW, fetcher=mock_fetch)
    assert result["orders_submitted"] == 0
    assert result["results"]["starting"] == 200
    assert result["results"]["observations"] == 60
    assert result["live_execution_verified"] is False

@pytest.mark.parametrize("symbol", ["", "../SPY", "spy", "SPY,QQQ", "A1"])
def test_invalid_symbol_rejected(symbol):
    with pytest.raises(ValueError, match="Invalid stock symbol"):
        run(symbol, "dummy", "dummy", now=NOW, fetcher=mock_fetch)

def test_insufficient_bars_rejected():
    def fetch(symbols, key, secret, *, now=None):
        return {"SPY": [{"t": (NOW - timedelta(days=2)).isoformat(), "c": 100}]}
    with pytest.raises(ValueError, match="Insufficient"):
        run("SPY", "dummy", "dummy", now=NOW, fetcher=fetch)

def test_current_day_bar_rejected():
    def fetch(symbols, key, secret, *, now=None):
        data = mock_fetch(symbols, key, secret, now=now)
        data["SPY"][-1]["t"] = NOW.isoformat()
        return data
    with pytest.raises(ValueError, match="Incomplete current-day"):
        run("SPY", "dummy", "dummy", now=NOW, fetcher=fetch)
