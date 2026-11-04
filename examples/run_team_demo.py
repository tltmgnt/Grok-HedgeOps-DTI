from hedgeops_team import HedgeOpsTeam

bars = [{"timestamp": "2026-01-%02d" % (i + 1), "close": 100 + i} for i in range(6)]
portfolio = {"equity": 200, "cash": 200, "exposure_pct": 0.0}
print(HedgeOpsTeam().analyze(bars, portfolio).to_dict())
