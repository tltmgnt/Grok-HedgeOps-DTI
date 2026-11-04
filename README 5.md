# Offline Paper Trader v2.0

Educational, long-only moving-average paper-trading simulator. Default starting
capital is **$200**. It has no API keys, network calls, broker integration,
short selling, or live-order capability.

## Run

```bash
python paper_trader.py --demo --capital 200
python -m unittest discover -s tests -v
python paper_trader.py --demo --capital 200 --json-out results.json --trades-out trades.csv
python paper_trader.py --csv historical_data/AAPL.csv --capital 200
```

CSV input requires a `close` column and optionally accepts `date`.

## Risk and interpretation

The default strategy uses 5/20 observation moving averages, a 0.1% fee per
transaction, and spends at most 25% of available cash on each entry. Results
are historical simulations, not forecasts or investment advice. The Sharpe
ratio is an annualized estimate based on observation-to-observation equity
returns and a 252-period convention; it is not meaningful for very short
series. The benchmark buys at the first observation and holds to the last.
