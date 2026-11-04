import pytest
from hedgeops_team import HedgeOpsTeam, RiskLimits

def bars(n=6):
    return [{"timestamp": "2026-01-%02d" % (i + 1), "close": 100 + i} for i in range(n)]

def portfolio(**overrides):
    return dict({"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0}, **overrides)

def test_deterministic_and_paper_only():
    team = HedgeOpsTeam()
    a = team.analyze(bars(), portfolio())
    assert a == team.analyze(bars(), portfolio())
    assert a.paper_only is True
    assert a.action == "BUY"
    assert 0 < a.suggested_position_pct <= 0.10

@pytest.mark.parametrize("bad", [
    [{"close": 100}],
    [{"close": 100}, {"close": float("nan")}],
    [{"close": 100}, {"close": 0}],
    [{"timestamp": "2026-01-02", "close": 100}, {"timestamp": "2026-01-01", "close": 101}],
])
def test_bad_bars_rejected(bad):
    with pytest.raises(ValueError):
        HedgeOpsTeam().analyze(bad, portfolio())

def test_drawdown_veto():
    result = HedgeOpsTeam().analyze(bars(), portfolio(drawdown_pct=0.25))
    assert result.action == "HOLD" and result.suggested_position_pct == 0

def test_exposure_veto():
    result = HedgeOpsTeam().analyze(bars(), portfolio(exposure_pct=0.3))
    assert result.action == "HOLD"

def test_short_history_hold():
    assert HedgeOpsTeam().analyze(bars(3), portfolio()).action == "HOLD"

def test_adapter_failure_closed():
    class Broken:
        def analyze(self, **kwargs):
            raise RuntimeError("unavailable")
    assert HedgeOpsTeam(strategic_agent=Broken()).analyze(bars(), portfolio()).action == "HOLD"

def test_invalid_limit():
    with pytest.raises(ValueError):
        RiskLimits(max_exposure_pct=2)
