# Daily Stock Discovery (read only)

This feature is a **research watchlist**, not an autonomous trading strategy. It does not submit orders, modify positions, or invoke the existing purchase workflow.

## How to run

After merging, go to **GitHub Actions → Daily Stock Discovery (Read Only) → Run workflow → main → Run workflow**.

The workflow also runs at **23:30 UTC on weekdays** (4:30 p.m. PST / 3:30 p.m. PDT); GitHub scheduled runs may be delayed, and the latest available IEX daily bar may be incomplete or stale depending on session timing. Inspect the report's `last_bar_utc` before acting. To change the timing, edit only this workflow's cron schedule.

It uses the existing **paper** repository secrets `ALPACA_API_KEY` and `ALPACA_API_SECRET` to make authenticated **GET-only** requests to Alpaca's historical stock-bars API. It does not need broker order permissions for its code path, although Alpaca keys themselves may have broader permissions; protect the credentials.

The run publishes a **job summary** and a downloadable `daily-stock-discovery-watchlist` artifact containing:

- `watchlist.md`: top 10 ranked symbols and risk indicators
- `watchlist.json`: machine-readable scores, observations and coverage

## Coverage and ranking

The scanner checks 20 explicitly defined symbols in `DEFAULT_SYMBOLS` in `stock_discovery.py`. It is **not** a market-wide stock screener. It fetches up to 120 calendar days of daily historical bars using Alpaca's **IEX** feed. Only symbols with at least 31 valid daily observations and a nonzero 20-day volume baseline are ranked.

The deterministic score combines:

- 20-session return (up to 40 points, can be negative)
- 5-session return (up to 25 points, can be negative)
- Latest IEX daily volume divided by previous 20-session average IEX volume (up to 20 points)
- Price above its 20-session simple moving average (+15 points)
- 20-session daily volatility penalty (up to 15 points)

The report also displays 30-session maximum drawdown. These are heuristic observations, **not a calibrated prediction**, buy recommendation, or estimate of expected returns.

**Important limitations:** IEX volume is not consolidated U.S. exchange volume; `adjustment=raw` prices do not adjust for splits or dividends; no news, financial statements, valuation, earnings, liquidity, spreads, or catalysts are checked. A high-ranked stock can lose money. The scheduled UTC time does not adjust for U.S. daylight-saving time. Review stale bars, split events, and independent sources before making decisions.

## Safety and troubleshooting

- The scanner only requests `https://data.alpaca.markets/v2/stocks/bars` with HTTP GET.
- It never imports `alpaca_purchase.py`, uses the trading API, or dispatches a purchase workflow.
- No secrets are written to the output or logs.
- Missing credentials, failed HTTP requests, unexpected API payloads, and no eligible symbols cause a failed run rather than a misleading report.
- An **HTTP 401** means the Alpaca service rejected the supplied key pair. In repository **Settings → Secrets and variables → Actions**, rotate/replace `ALPACA_API_KEY` and `ALPACA_API_SECRET` together with a currently active, matching **paper-account** key ID and secret. The workflow cannot repair revoked or mismatched credentials; do not post keys in issues, logs, run inputs or chats. Do not switch to live trading credentials as a workaround.
- After replacing both secrets, manually run **Alpaca Paper API Connection Test** (a GET-only check), then **Daily Stock Discovery (Read Only)**. A paper account check passing does not guarantee separate market-data entitlement; verify the scanner's result too.
- HTTP 403 or other errors can reflect feed entitlements or API policy. Inspect the redacted error and confirm the account has access to the IEX historical daily-bar feed. Do not bypass authentication or substitute synthetic bars for a real watchlist.
- The existing approved paper-order workflow remains separate and unchanged.

For offline tests: `python -m unittest tests.test_stock_discovery` (or `python -m unittest discover -s tests -p 'test_stock_discovery.py'`).
