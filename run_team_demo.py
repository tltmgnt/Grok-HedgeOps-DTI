from hedgeops_team import HedgeOpsTeam

prices = [100, 100.5, 101, 100.8, 101.4, 102, 102.2, 103, 103.5, 104]
report = HedgeOpsTeam().analyze(
    [{"timestamp": f"t{i}", "close": price} for i, price in enumerate(prices)],
    {"equity": 200, "cash": 200, "exposure_pct": 0, "drawdown_pct": 0},
)
print(report.to_dict())
