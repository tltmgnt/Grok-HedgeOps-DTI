# Free offline paper trading (iPad / GitHub Codespaces)

This standalone educational simulator does **not** connect to Grok, exchanges, brokers, live market data or the HedgeOps decision workflow. It never places orders or sends network requests.

From the repository root in your Codespaces terminal:

```bash
python paper_trader.py --demo --capital 200
python -m pytest -q
```

The demo generates repeatable **synthetic** prices, simulates a 5/20-period moving-average crossover, charges a modeled 0.1% fee per buy/sell, and caps each new purchase at 25% of available cash. It reports ending equity, returns, maximum drawdown, and trades. Results are not predictive of real-world performance. No hard daily-loss stop or 1%-risk sizing is implemented; do not use for live trading.

For your own historical prices, upload a CSV with `date,close` headers and run:

```bash
python paper_trader.py --csv prices.csv --capital 200
```

Only use trusted data files. No API key or paid credits required. Stop Codespaces after use to conserve your cloud allowance.

This is a first simulation step, **not** an unattended 24/7 bot. Live market feeds, execution, alerts, monitoring, safety controls, and an always-on host would require separate development and testing.
