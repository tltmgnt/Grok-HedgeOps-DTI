# Autonomous paper experiment

This implements a bounded forward experiment, not a profitable strategy or a
live-money release. Version: `momentum-news-v1`. No live broker host is accepted.
The 20-symbol universe, score, completed daily-bar trend, volume, volatility,
drawdown and headline-presence gates remain in `paper_opportunity_intelligence.py`.
These are observations and assumptions, not fundamental valuation or proof of causality.
No paid LLM is required or allowed to direct orders in this experiment.

## Monday setup

In GitHub Settings → Environments → **paper-trading**, configure the same dedicated
paper-only secrets as the manual paper workflow:

- `ALPACA_PAPER_API_KEY`
- `ALPACA_PAPER_API_SECRET`

Do not paste credentials into chat, commits, Actions inputs or screenshots.
Environment approval requirements must permit scheduled runs if unattended
execution is desired. This code does not change environment protection settings.
Secrets cannot be verified from source control or offline tests.

The scheduled workflow is **Autonomous Paper Sessions**. It runs at minutes 17 and
47, 13–21 UTC on weekdays, then consults the broker clock for holidays and actual
market hours. On November 9, 2026 the first planned open-market slot is 14:47 UTC
(9:47 a.m. Eastern / 6:47 a.m. Pacific). Actions can start late or be skipped.
Manual dispatch defaults to **monitor_only = true**. Run that first and inspect
`session.json`, `entry/decision.json` and the job summary before a paper order run.

On merging this change, scheduled PAPER execution defaults to enabled. Existing
repository/environment variables override it:

| Variable | Default | Effect |
|---|---|---|
| `PAPER_AUTO_TRADING_ENABLED` | `true` | Set `false` to disable new entries and exits |
| `PAPER_AUTO_KILL_SWITCH` | `false` | Set `true` to disable new entries and exits |
| `PAPER_DATA_FEED` | `iex` | `sip` requires an entitled Alpaca data subscription |

Kill switches prevent future submissions; they do not cancel broker orders already
accepted. Use Alpaca's paper account to reconcile or cancel those. The legacy manual
order workflows remain available; do not operate them concurrently with this worker.
All opportunity order workflows share a concurrency group to reduce this risk.

## Fixed experiment rules

- One $10 entry attempt per Eastern trading date, $100 account-wide daily buy
  commitment cap, five total account positions, and $100 minimum post-order cash reserve.
- New entries also require current and prior-close broker equity: block buys at
  an account-wide equity decline of 1% or more, limit each fixed-size buy to 2%
  of current equity, and require post-entry gross position market value at most
  20% of current equity. Long and short market values count by absolute value;
  pending sells do not release exposure. Missing or invalid evidence fails closed.
  These entry gates are rechecked immediately before submission and do not block
  strategy exits. The $10 size is never increased or resized to pass a gate.
  Equity change includes all account activity and can be distorted by cash flows;
  it is not a cash-flow-adjusted daily P/L measure or a forced-liquidation rule.
- News presence and momentum are unproven entry hypotheses. A headline keyword is
  not verification that an earnings event is good, novel, or causally relevant.
- Before each entry/exit POST, require a bid/ask quote no older than 120 seconds,
  no future timestamp, positive uncrossed prices, and spread at most 0.5%.
- Daily signals use completed historical **IEX** bars. `PAPER_DATA_FEED=sip` changes
  the fresh quote guard only; this does not silently mix signal feed definitions.
- Sell at a broker-observed loss of at least 3%, gain of at least 6%, or after five
  calendar days. These are arbitrary preregistered experiment settings, not optimized
  thresholds or broker-native protective stops. Gaps and outages can exceed them.
- Exit only an exact unmixed long lot proven by a fully filled strategy buy and
  complete broker order history. Unknown/manual holdings are left for review.
- Pending orders block entries; deterministic IDs prevent duplicate entries and
  exits. POSTs are never retried after timeouts. Exit intents are written before POST.
- Rejected/ambiguous orders require broker inspection. A stable failed exit ID is
  not replaced automatically with a new sell ID.
- A no-trade day is a valid outcome. Missing credentials, malformed history,
  quote errors and API failures produce a failed job, not a success claim.

## Evidence and evaluation

Every Actions run retains status, assessment, timestamps, signal metrics, catalyst
headlines, quote feed and quote timestamp, acknowledgments and exit intents for
90 days. Download evidence before expiry if retaining a longer study. No credentials
or account IDs are saved. The repository is public: evidence may be accessible to
other users; use a private repository before retaining sensitive account data.

Portfolio observations are account-wide, include manual activity, and can be
confounded by deposits/withdrawals. They are not strategy-specific alpha, realized
trade P/L, or cash-flow-adjusted returns. A submitted order is not a confirmed fill.
The worker reconciles broker history on later sessions. Current reporting does not
yet calculate isolated FIFO trade attribution, trading costs or benchmark excess
returns. It must not certify readiness for live money.

Keep the rules fixed across future sessions. Evaluate losing trades, skipped trades,
failures, drawdowns, execution differences and all strategy versions. Compare with
an investable benchmark on matching dates with explicit slippage/fee assumptions;
reserve unseen sessions for evaluation. Increasing size is not validated by picking
only successful historical trends. No minimum number of paper days establishes a
profitable edge by itself.

## Frequent current-data observations

Actions scheduling is not a continuous real-time service. An optional persistent
worker polls at 60-second intervals on a continuously running machine:

```sh
python -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
# Supply ALPACA_API_KEY / ALPACA_API_SECRET securely in the process environment.
# These must be dedicated PAPER keys. The process never selects a live host.
export PAPER_AUTO_TRADING_ENABLED=true
export PAPER_AUTO_KILL_SWITCH=false
export PAPER_ALLOCATION_MODE=legacy
export PAPER_REQUIRE_FRESH_QUOTE=true
export PAPER_DATA_FEED=iex
.venv/bin/python paper_research_worker.py --monitor-only
# After a verified rehearsal, omit --monitor-only for the paper experiment.
```

Use one worker only, with a persistent `data/paper-research` volume and backups.
Disable the Actions workflow while this worker executes orders: GitHub concurrency
does not lock external processes. The worker stops on any error and requires
reconciliation before manual restart. Polling is not tick-by-tick streaming. A
hosted runtime, deployment, uptime monitoring and streaming integration are not
provisioned by this repository change.

## What to pay for

As checked November 7, 2026, Alpaca documents Basic as free (IEX real-time coverage)
and Algo Trader Plus as $99/month (all U.S. exchanges). The free feed is sufficient
for this paper pilot. Paying for SIP does not improve the strategy by itself.
Standard hosted GitHub runners on public repositories are free; artifact storage
has separate allowances. xAI API usage is optional and metered; it is not required
by this deterministic worker. An always-running host is a separate deployment choice.

Sources: https://docs.alpaca.markets/us/docs/about-market-data-api and
https://docs.github.com/en/billing/concepts/product-billing/github-actions .
