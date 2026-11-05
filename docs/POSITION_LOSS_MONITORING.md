# Position-loss monitoring and protective exits

## Current scope

The `position_loss_monitor.py` command reads Alpaca's `GET /v2/positions` endpoint. It compares broker-reported **unrealized profit/loss** against **cost basis**, and labels each long position `ok`, `warning`, or `critical`. This is not intraday loss monitoring, streaming quotes, portfolio peak-to-trough drawdown, or a broker stop order. It is not a recommendation to sell.

The default alert levels are 5% and 10%. These are examples only; select thresholds appropriate to your own strategy and risk tolerance. It does not check market-data timestamps or guarantee quotes are current. Missing, inconsistent, non-finite, or negative position data causes monitoring to fail rather than guess.

## Setup

1. In repository Settings → Environments, create `broker-monitoring` and restrict it to the trusted `main` branch. For scheduled jobs, avoid required reviewers unless you intend to approve each run.
2. Add environment secrets `MONITOR_ALPACA_API_KEY` and `MONITOR_ALPACA_API_SECRET` for the **same account** selected by the monitor. Prefer keys with enforced read-only permissions if supported. Merely using GET requests is not equivalent to credential-level read-only restrictions.
3. Optionally set `HEDGEOPS_ALERT_WEBHOOK` to a private HTTPS endpoint that accepts `{"text": "alert details"}` as JSON. Alerts contain tickers and loss percentages; only use an endpoint you trust. Without this secret, the monitor produces no external notification.
4. To monitor the live account on the weekday schedule, set the environment variable `MONITOR_SCHEDULE_MODE` to `live` after reviewing credentials and alert privacy. The default is `paper`.
5. Use Actions → Read-only Position Loss Monitor → Run workflow to test manually.

The workflow runs every 30 minutes during 14:00–21:59 UTC on weekdays. It is **not continuously running** and does not filter holidays or guarantee execution. The scheduled job skips safely if credentials are absent. An unavailable API or failed notification marks the job failed. Logs and job summaries show only alert counts; full reports are not uploaded to GitHub Actions artifacts because this is a public repository.

## Alert example

A position with a $100 broker-reported cost basis and a $94 market value has a 6% unrealized loss, triggering the default warning. At $89 market value, the loss is 11%, triggering critical. These calculations do not predict the next price or account for future execution slippage.

## What is deliberately not implemented

- No automated selling, stop-loss order placement, broker-side bracket orders, or kill-switch modifications to the account.
- No duplicate alert suppression, push-stream price updates, quote freshness verification, market calendar integration, or guaranteed notifications.
- No Webull, Webull Pay, IBKR or Merrill position monitoring; those broker integrations require separate authorized adapters.
- No continuous background daemon. GitHub Actions scheduling is best effort and may not run on time.

For reliable protective exits, use broker-supported risk controls after independent review, paper testing, authentication hardening, and order/position reconciliation. **Stop-market orders can fill below the stop price, and stop-limit orders may not fill at all.**
