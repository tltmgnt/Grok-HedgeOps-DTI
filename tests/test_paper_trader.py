import pytest
from paper_trader import prices_demo, simulate

def test_repeatable_and_no_leverage():
    a = simulate(prices_demo(), capital=200)
    b = simulate(prices_demo(), capital=200)
    assert a == b
    assert a["ending"] > 0
    assert a["max_drawdown_pct"] >= 0
    assert all(t[1] in ("BUY", "SELL") for t in a["trades"])

def test_empty_prices_rejected():
    with pytest.raises(ValueError):
        simulate([])

def test_invalid_price_rejected():
    with pytest.raises(ValueError):
        simulate([("today", -1)])

def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        simulate(prices_demo(), capital=-1)
