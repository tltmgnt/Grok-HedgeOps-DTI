# HedgeOps Team: offline decision support

This additive package does not import or modify paper_trader.py and has no broker or order interface.

Run from repository root:

```bash
python -m pytest tests/test_hedgeops_team.py -q
python examples/run_team_demo.py
```

The deterministic team validates finite positive closes, strictly ordered optional ISO timestamps, and portfolio constraints. It returns HOLD on insufficient history, risk vetoes, or strategic disagreement. All decisions are paper-only and include a SHA-256 input digest and evidence records.

The optional strategic_agent must expose analyze(bars=..., portfolio=...) returning an object or mapping with action BUY, SELL or HOLD. Failures and invalid actions fail closed to HOLD. No external model is instantiated by default.

This is an initial implementation, not a calibrated forecasting system. No live trading integration, xAI connectivity verification, or backtest performance claim is provided.
