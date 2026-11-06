# Trade qualification and order feedback

This feature is **paper-only**. The scheduled job is dry-run and never connects to a broker. The separate order workflow requires manual dispatch, exact authorization, and a GitHub environment named `paper-order-approval` with required reviewers. Do not configure production credentials in that environment.

## Data contract
Set the GitHub Actions repository variable `PAPER_MARKET_SNAPSHOT_JSON` to a JSON object containing `signals` (array), `account` (equity, buying_power, daily_pnl), `positions` (array), and `orders` (array). Example:
```json
{"account":{"equity":10000,"buying_power":1000,"daily_pnl":0},"positions":[],"orders":[],"signals":[]}
```
The snapshot is not fetched by this prototype. No data provider or Grok integration is implied. Missing or stale inputs fail closed. A producer must populate verifiable, timestamped observations; do not put private account details in a public repository variable. Use synthetic account inputs for dry runs. Grok can annotate or veto a candidate via `grok_veto` but cannot override any gate. No autonomous AI order selection is enabled.

Each signal needs `symbol`, `price`, `sma20`, `sma50`, `volume`, `avg_volume`, `spread_bps`, `asof` (UTC ISO 8601), `market_open`, and `tradable`. Entry: price > SMA20 > SMA50, volume >= average, spread <= 20 bps, age <= 15 minutes. Risk caps: max $200 or 2% equity per trade, max 20% total long exposure, max 5 positions, stop at 1% daily loss. These are experimental and not validated against historical data.

**Important limitations:** The manually dispatched order job currently uses a supplied snapshot rather than a fresh broker portfolio reconciliation, so it is a prototype and should not be enabled with credentials until live account/position/order retrieval, order idempotency and test coverage are completed. An accepted order is not necessarily filled. Broker failures can have ambiguous outcomes: reconcile in Alpaca before retrying. Live trading is never enabled by these workflows.
