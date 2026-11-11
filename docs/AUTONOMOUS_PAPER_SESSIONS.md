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

The scheduled workflow is **Paper Research Agent**. It runs at minutes 17 and
47, 13–21 UTC on weekdays, then consults the broker clock for holidays and actual
market hours. Scheduler times are in UTC; actual local market times shift with daylight
saving time, and jobs may start late or be skipped. Actions can start late or be skipped.
Manual dispatch defaults to **monitor_only = true**. Run that first and inspect
`session.json`, `entry/decision.json` and the job summary before a paper order run.

The hardened workflow runs every **scheduled** and **push** session in
monitor-only mode, with no new PAPER broker orders. To test the broker-executing
path requires an explicit, reviewed **manual** workflow dispatch with
`monitor_only=false`, a protected `paper-trading` environment and all
the approved settings below. This is NOT continuous streaming execution;
the strategy uses completed IEX daily bars and a fresh quote guard.

| Variable / secret | Default | Effect |
|---|---|---|
| `PAPER_AUTO_TRADING_ENABLED` | `false` | Must be explicitly `true` for any automated entry or exit |
| `PAPER_AUTO_KILL_SWITCH` | `true` | Must be explicitly `false` for broker execution |
| `PAPER_BROKER_EXECUTION_APPROVED` | `false` | Additional protected manual execution approval |
| `PAPER_LEDGER_DATABASE_URL` (secret) | absent | Durable PostgreSQL ledger required before every automatic buy POST |
| `PAPER_REGIME_CONTROL_ENABLED` | `true` | Must remain enabled for broker-executing sessions |
| `PAPER_REGIME_REVIEW_APPROVED` | `false` | Must be separately approved, with valid signed bull evidence |
| `PAPER_DATA_FEED` | `iex` | `sip` requires an entitled Alpaca subscription |

The evidence file, approved digest, expiry, Ed25519 public-key fingerprint,
public key and signature must also be provided as described in
[PAPER_REGIME_ENTRY_CONTROL.md](PAPER_REGIME_ENTRY_CONTROL.md).
For manual broker-capable workflow dispatches, provide
`PAPER_REGIME_EVIDENCE_JSON_B64` as a **protected environment secret**:
the base64 encoding of the exact reviewed, signed regime-evidence JSON
bytes. The runner decodes it into a mode-0600 temporary file, sets the
runtime evidence-file path, and never uploads that file as an artifact.
The environment's approved SHA-256 digest must match those exact bytes.
The expiry, key, pinned key fingerprint and signature must be maintained
independently in protected environment variables. Do not place the
private signing key in GitHub Actions, or log/copy the evidence to the
workflow summary. This secret-delivery path is only used for an
explicitly broker-capable manual run; scheduled observation does not
require it.
The reference prototype regime thresholds are **not empirically validated**.
Until independent risk, statistical, source, and key-management review,
**do not activate any new broker entry**. A BULL label never authorizes
trading by itself. The signing private key must not be available to the runner.

The PostgreSQL `paper_order_ledger` table must be provisioned by an
authorized DB migration operator **before** manual dispatch; the runner
does not create its own database schema. Use a restricted DB role and
TLS, with independently administered secret access. The actual automatic
broker POST flows through `PostgresPaperLedger` and `submit_with_ledger`:
commit the attempt first; on retry/restart, reconcile the same client order
ID only. A broker 404 does not make a reserved intent safe to POST again.
The workflow installs pinned PostgreSQL and Ed25519 verifier drivers.
Their hashes and dependency graph must be integrated into the repository's
reproducible dependency locks before operational activation.

This workflow uses dedicated `ALPACA_PAPER_API_KEY` and
`ALPACA_PAPER_API_SECRET` only; there is no fallback to live keys.
No orders are placed by CI or these changes alone.

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
