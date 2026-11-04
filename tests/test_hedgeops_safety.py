"""Increment 1: fail-closed validation and paper-only regression coverage."""
from datetime import timedelta
import pytest
from hedgeops_team import HedgeOpsTeam
from hedgeops_team.feedback import Forecast, evaluate

def bars(n=6):
    return [{"timestamp": "2026-01-%02d" % (i + 1), "close": 100 + i} for i in range(n)]

def portfolio():
    return {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}

@pytest.mark.parametrize("missing", ["equity", "cash", "exposure_pct", "drawdown_pct"])
def test_missing_portfolio_fields_rejected(missing):
    p = portfolio()
    del p[missing]
    with pytest.raises(ValueError, match="missing portfolio field"):
        HedgeOpsTeam().analyze(bars(), p)

@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf"), True, "101"])
def test_invalid_forecast_reference_price_rejected(invalid):
    with pytest.raises(ValueError):
        Forecast("2026-01-01", "2026-01-02", "BUY", invalid)

@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf"), True, "101"])
def test_invalid_realized_price_rejected(invalid):
    forecast = Forecast("2026-01-01", "2026-01-02", "BUY", 100)
    with pytest.raises(ValueError):
        evaluate(forecast, "2026-01-03", invalid)

@pytest.mark.parametrize("action", ["BOGUS", "REJECT", "", None])
def test_invalid_forecast_action_rejected(action):
    with pytest.raises(ValueError):
        Forecast("2026-01-01", "2026-01-02", action, 100)

def test_equivalent_timezone_offsets():
    forecast = Forecast("2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", "BUY", 100)
    assert evaluate(forecast, "2026-01-01T20:00:00-05:00", 101)["direction_correct"]

def test_mixed_timezone_rejected():
    with pytest.raises(ValueError, match="mixed timezone"):
        Forecast("2026-01-01T00:00:00", "2026-01-02T00:00:00+00:00", "BUY", 100)

def test_utc_normalized_bars_and_interval():
    bs = bars()
    for i, bar in enumerate(bs):
        bar["timestamp"] = "2026-01-%02dT19:00:00-05:00" % (i + 1)
    result = HedgeOpsTeam(expected_bar_interval=timedelta(days=1)).analyze(bs, portfolio())
    assert result.paper_only

def test_irregular_bars_rejected_when_interval_configured():
    bs = bars()
    bs[4]["timestamp"] = "2026-01-07"
    bs[5]["timestamp"] = "2026-01-08"
    with pytest.raises(ValueError, match="unexpected bar interval"):
        HedgeOpsTeam(expected_bar_interval=timedelta(days=1)).analyze(bs, portfolio())
    assert HedgeOpsTeam().analyze(bs, portfolio()).paper_only

def test_sell_is_directional_only():
    bs = bars()
    for i, bar in enumerate(bs):
        bar["close"] = 110 - i
    report = HedgeOpsTeam().analyze(bs, portfolio())
    assert report.action == "SELL"
    assert report.sell_semantics == "directional_signal_only"
    assert report.suggested_position_pct == 0
    assert report.paper_only

@pytest.mark.parametrize("interval", [0, -1, "daily"])
def test_invalid_interval_configuration(interval):
    with pytest.raises(ValueError):
        HedgeOpsTeam(expected_bar_interval=interval)
