# Paper Opportunity Intelligence — automated paper orders (OFF by default)

This new workflow is **paper-only**. It does not change or call the existing `paper-trading.yml`, and cannot reach Alpaca's live-trading host. It runs on weekdays at 19:00 UTC (11:00 a.m. PST / noon PDT) and can also be dispatched manually. GitHub may delay scheduled workflows.

## Activation — read carefully

**Merging the PR does not enable trading.** The entire job is skipped unless BOTH GitHub repository **Settings → Secrets and variables → Actions → Variables** are configured exactly:

- `PAPER_AUTO_TRADING_ENABLED` = `true`
- `PAPER_AUTO_KILL_SWITCH` = `false`

If either variable is missing, misspelled, or different, no trading job starts. For a **kill switch**, change `PAPER_AUTO_KILL_SWITCH` to `true` or `PAPER_AUTO_TRADING_ENABLED` to `false`. This prevents **new** jobs from submitting; it **does not cancel orders already accepted by Alpaca**, and cannot interrupt a job that already read the flag. To stop an in-flight run, cancel it in GitHub Actions, then inspect/cancel open orders in Alpaca Paper Trading.

The workflow uses existing repository secrets `ALPACA_API_KEY` and `ALPACA_API_SECRET` for the **paper** account. Do not use live keys. It does not use GitHub's human-review environment because this mode is explicitly unattended.

## Opportunity intelligence

The system retrieves the existing 20-symbol watchlist's historical **IEX** daily bars, scores each symbol using the same deterministic discovery metrics, and considers only the highest-ranked candidate that meets all of:

- Score at least 60; positive 5- and 20-session momentum
- 5-session return at most 12%; 20-session return at most 25%
- Relative IEX volume 1.2–4.0; above 20-session average
- 20-session daily volatility at most 3%; 30-session maximum drawdown at most 12%
- Data no older than 5 days; asset active, tradable and fractionable
- At least one Alpaca news headline in the last 7 days containing a specified catalyst keyword

**News headlines are evidence of an event mention, NOT verified positive sentiment or fundamentals.** Earnings-calendar checks, SEC filings, valuation, financial statements, consolidated volume, and detailed catalyst verification are not yet implemented. This is a conservative rule-based prototype, not an AI-powered prediction. It may make no trades for long periods. The feed is IEX, not consolidated U.S. market volume; prices are unadjusted for splits and dividends.

## Risk controls

- Fixed **$10 maximum notional** per order, one order attempt per trading day, and one candidate per run.
- Broker cash and buying power must each be at least **$100** before buying; paper account must be ACTIVE and unblocked.
- At most **five existing positions** before a new purchase.
- No purchase of the chosen symbol if already held or if it has an open order.
- Any existing open buy order pauses the automation (including the earlier SPY paper order).
- The broker's recent order history is checked for today's automated client IDs. If history is unavailable or truncated, trading stops.
- Every order uses a deterministic `client_order_id` based on U.S. Eastern trading date and symbol.
- Broker lookup for the same client ID must return HTTP 404 before submission. Any other error stops the run.
- Only `POST https://paper-api.alpaca.markets/v2/orders` can submit an order. No live host, no automatic POST retry.
- The result is written to a GitHub Actions summary and a 30-day `paper-opportunity-intelligence-decision` artifact. `SUBMITTED` is **not** proof of a fill.

**Limits and caveats:** These are order-size and count controls, not a portfolio-wide loss limit or a guaranteed daily dollar cap across other trading systems. A broker-side accepted order can remain open or fill later. GitHub repository variables are not a real-time broker-side kill switch. The order-history query covers a recent window and should be extended for production-grade persistent risk accounting. The current scanner checks only the 20 predefined symbols, not the entire market.

## Safe rollout

1. Merge PR only after reviewing the workflow and passing tests.
2. Leave the enable variable unset. Manually run the workflow and confirm the job is **skipped**.
3. Inspect the code and paper account, including open orders. Verify that no live credentials are used.
4. When you intentionally choose unattended paper trading, set both variables as above.
5. Monitor GitHub Actions and Alpaca **Paper Orders** after each run. Never blindly rerun an ambiguous submission.

To run offline tests: `python -m unittest discover -s tests -p 'test_paper_opportunity_intelligence.py'`.

**No new paper orders are submitted by creating or merging this PR.**
