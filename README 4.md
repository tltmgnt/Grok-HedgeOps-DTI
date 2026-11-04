# Paper Trader v2.0

Offline-only educational paper trading. No API keys, network access, broker connections, or live orders.

## Run

```bash
python paper_trader.py --demo --capital 200
python -m unittest -v
```

Optional reports:

```bash
python paper_trader.py --demo --capital 200 --json-out results.json --trades-out trades.csv
```

CSV input:

```bash
python paper_trader.py --csv historical_data/AAPL.csv --capital 200 --fast 5 --slow 20
```

Optional risk settings:

```bash
python paper_trader.py --demo --capital 200 --max-allocation 0.25 --stop-loss 0.08
```

`--stop-loss 0.08` means an 8% stop-loss relative to the entry price.
`--force-liquidate` closes any remaining position at the final observation. By default, open positions are marked to market.

Signals use only prior observations and execute at the current observation price. This is a simple educational long-only moving-average regime strategy, not investment advice or a production trading system.
