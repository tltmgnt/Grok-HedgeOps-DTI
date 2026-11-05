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

## GitHub Actions: Purchase Now (paper request only)

From the repository **Actions** tab, select **Offline Paper Trading** → **Run workflow**. Select the `purchase_now` action and supply:

- `symbol`: uppercase ticker-like identifier (e.g. `SPY`); this is not verified against an exchange.
- `notional_usd`: a requested illustrative dollar amount between $0 and $200 (exclusive of $0).

The workflow validates the inputs using `purchase_now.py` and uploads a `purchase-now-paper-request` JSON artifact. The artifact contains a timestamp, requested symbol and notional, `pending_human_review` status and explicit flags `order_submitted=false` and `order_executed=false`.

**Important:** The button label describes only a purchase *request*. It does not perform either a live or simulated broker purchase. It has no quote freshness checks, account-risk controls, broker connectivity, or execution authority. GitHub runners are not trading execution hosts. The $200 cap is merely a demo input limit, not a statement about account funds or risk. Any future live trading must use a separately reviewed, explicitly authorized, deterministic broker-execution system.

To generate the same request offline:

```bash
python purchase_now.py --symbol SPY --notional 25 --output purchase-request.json
```

Scheduled paper simulations continue to run under the `simulate` action and never submit orders.
