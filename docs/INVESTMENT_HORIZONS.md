# Investment horizon research and paper execution

This workflow evaluates MSFT and GOOGL under separate **1–2 year** and **5 year or
longer** scenarios. It produces an auditable research report and supports an
explicitly requested, gated paper entry. It cannot route orders to a live host.
It does not establish that these stocks are undervalued or will recover.

## Run the workflow

Actions → **Investment Horizon Research and Paper Entries** → **Run workflow**.
Leave `paper_entry=false` for research, or choose a horizon and request one paper
entry. Manual paper requests additionally require the enable variables below.
The scheduled weekday run at **19:35 UTC** evaluates both horizons and **never
requests execution**. GitHub may delay or skip it; the code rechecks data freshness
and, for an entry, the broker clock. There is no continuous monitoring claim.

The workflow is restricted to `main` and uses the existing `paper-trading`
environment. It shares the automated paper session's concurrency group to serialize
those two workflows. Manual purchases, other tools and external broker activity
can still race these checks; the limit price and broker acceptance remain relevant.

Provide dedicated paper market-data credentials using the existing
`ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_API_SECRET` secrets. The existing generic
secret names are fallback aliases; operators must ensure they contain **paper**
credentials. The code hardcodes Alpaca's paper host and accepts no custom host.
`PAPER_DATA_FEED` chooses `iex` or entitled `sip`. Missing credentials or failed
quotes produce a saved error report and a failed job, not readiness.

Outputs, retained for 90 days, are `research.json`, `summary.md` and, only when
execution reaches an order intent, `entry-intents.jsonl`. Research includes each
candidate, horizon, evidence timestamps, policy fingerprint, scenario values,
entry ceiling and failed gates. The intent is flushed to disk before POST.
Artifacts only survive if upload succeeds; an interrupted runner is not durable
broker evidence. On timeout, reconcile the deterministic client order ID in Alpaca
before retrying. A green job, accepted order or paper fill is not investment profit.

## Valuation policy and evidence

`research/investment_policy.json` preserves the workbook's illustrative price
ranges and assumptions. It deliberately starts with **unreviewed, annualized
single-quarter EPS** and all financial review checks false. These inputs cannot
release an order, even if the price falls into the entry zone. There is no
fundamentals provider integration and no invented approval or updated review date.

For a real research review, replace the starting EPS with reconciled annual per
share earnings; set `eps_basis=reviewed_annual`; record actual `reviewed_at`,
`financials_as_of` and public HTTPS `sources`; and attest the five specific checks:
annual earnings reconciliation, cash flow, debt, dilution and an intact thesis.
The review must be no older than 90 days and financials no older than 180 days;
future or timezone-free timestamps are rejected. This is a documented operator
attestation, not independent verification or an AI review. Submit policy changes
through normal code-owner review. Never refresh timestamps without doing the work.
Only public data and deliberately publishable research belong in this repository
or its public workflow artifacts. Keep private account data and proprietary
research outside it, following [the publication boundary](IP_BOUNDARY.md).

For each scenario:

```
value = annual EPS * (1 + EPS growth)^years * terminal PE
entry ceiling = base scenario value / (1 + required return)^years
price cap = min(entry zone upper bound, entry ceiling)
```

The input 12% required return is a chosen hurdle, not an expected return. Scenario
values exclude dividends, taxes and fees; bear values are not worst-case bounds.
The two year model must be rebuilt before making a one year exit commitment.
A quote is usable only with a positive, uncrossed bid/ask, age 0–120 seconds and
spread at most 0.5%. The **ask** must be within the entry zone and price cap.
These are project settings, not universal investment standards.

States are `EVIDENCE_REQUIRED`, `WATCH` (review passed but price failed), and
`REVIEW_READY`. Readiness is a research status, not an execution instruction.
Every missed financial check is recorded alongside price failure. One failed gate
cannot be overridden by another passing gate or a falling stock price.

## Paper entry requirements and lifecycle

All these conditions are necessary:

- Manual dispatch with `paper_entry=true` and the chosen `horizon`.
- `INVESTMENT_PAPER_ENABLED=true` and `PAPER_AUTO_TRADING_ENABLED=true`.
- `PAPER_AUTO_KILL_SWITCH=false` and legacy allocation mode.
- A fresh assessment at execution time with reviewed financials and an entry price
  inside its zone. A saved READY record is never accepted as authorization.
- Existing account checks: active/unblocked account, cash reserve, buying power,
  2% equity entry cap, 20% gross exposure cap, daily account loss guard, position
  count, open order reconciliation and $100 daily buy commitment cap.
- No existing holding in the selected symbol, an eligible fractionable asset,
  no prior investment attempt that trading day across either horizon, and a final
  fresh quote, clock and enable check.

At most one **$10 paper buy limit order** is attempted per invocation. The limit
price is rounded down to cents and cannot exceed the valuation/zone cap. It is a
day order without extended-hours opt-in; it can expire or remain unfilled. There
is no market-order fallback, automatic averaging down, tranche expansion or POST
retry. Alpaca's [fractional order documentation](https://docs.alpaca.markets/us/docs/fractional-trading)
describes day-limit support for notional orders; authenticated acceptance remains
unverified until an authorized qualifying request is actually tested. A rejection
must be investigated, not worked around by weakening the price cap.

Client IDs follow `ho-invest-YYYYMMDD-HORIZON-symbol`, using the New York trading
date. Only an explicit not-found response permits a POST; other lookup failures
block. A known existing order is reported as `ALREADY_EXISTS`. An uncertain POST
or malformed acknowledgment produces `UNKNOWN_RECONCILE` and a failed CLI run.
`SUBMITTED` is an acknowledged request, not a guaranteed fill. Filled status also
requires a positive filled quantity and valid average fill price. Partial fills
remain broker exposure; inspect the actual broker order and position.

**Holding management:** these IDs are excluded by the momentum strategy's exact
ID check, so its 3% loss, 6% gain and five-day exits do not apply. This addition
implements entries, not automated investment sales. Review holdings quarterly,
after material business events, and at the chosen horizon deadline. A horizon is
not a promise to hold through a broken thesis. No live execution, automatic sell,
stop order, user notification, AI challenge or recurring broker holding review is
activated by this change. Existing account exposure checks still count these lots.

## Local verification

```sh
python -m unittest discover -s tests -p 'test_investment*.py' -v
python investment_research.py --output /tmp/investment-research
# Explicit paper entry only after valid reviews, credentials and enable settings:
python investment_research.py --paper-entry --horizon 5y --output /tmp/investment-research
```

Tests use synthetic fixtures only and verify valuation arithmetic, both horizons,
stale/malformed evidence, gates, price changes, paper-only bounded requests,
duplicate reconciliation, uncertain submissions and isolation from momentum exits.
The existing complete pytest suite remains the regression check.

### Offline decision-to-fill trace

New runs add a `research_run_id` to `research.json` and to the durable
`PAPER_ENTRY_INTENT` journal record. The final assessment in the journal
uses the submission-time quote, which can differ from the earlier research
snapshot. The trace links the journal to a separately saved paper broker
order by client order ID and checks the broker order ID when the submission
acknowledgment recorded it.

```bash
python investment_paper_trace.py investment-output/research.json \
  --intents investment-output/entry-intents.jsonl \
  --paper-order-snapshot paper-order.json
```

Supply an order JSON from the paper environment. The tool reads local files
and prints an audit record. It reports a skipped submission, missing broker
evidence, or a matched snapshot or discrepancy. Fill quantity and average
price are cumulative broker observations. A snapshot does not establish
individual fills, position or cash reconciliation, or the source's
authenticity. An existing order detected on a subsequent run is attributed
only through the original run's journal. Historical reports without a run
ID cannot be joined automatically.

Add `--accounting-evidence paper-accounting.json` to reconcile individual
paper fills, fees, position quantity, and cash. Use normalized USD evidence
from a single paper account with no unrelated trades, cash movements, or
position adjustments during the interval. Use a local account alias for
`account_ref`. The broker order snapshot must include its timezone-aware
`updated_at`. Obtain the order snapshot and ending balances for the same
cutoff with no intervening account activity.

The accounting JSON has these fields:

| Record | Fields |
| --- | --- |
| Top level | `mode` set to `PAPER_ONLY`, `isolated_interval` set to true, `account_ref`, `before`, `after`, `fills` |
| Before and after | `account_ref`, `symbol`, `currency` set to `USD`, `observed_at`, `position_qty`, `cash` |
| Each fill | `account_ref`, `symbol`, `currency`, `fill_id`, `broker_order_id`, `side` set to `buy`, `executed_at`, `qty`, `price`, `fee` |

Supply timezone-aware timestamps, stable activity IDs, and decimal strings
for amounts. Use an explicit zero fee only when the source confirms it.
Supply balances on a trade-date cash basis and preserve execution precision.
The tool sorts fills, deduplicates matching activity IDs, and rejects
conflicting copies. It compares cumulative quantity with the order snapshot,
checks each fill against the limit, and shows the expected and observed
position and cash with exact differences. Source authentication, settlement
timing, unrelated activity, and multi-order accounting require separate evidence.

### Multi-order paper account reconciliation

Run `python investment_paper_portfolio.py paper-portfolio.json` to reconcile
overlapping traced buy orders and signed non-trade cash movements against
one pair of account snapshots. It prints JSON and exits 0 for matching
balances, 1 for discrepancies, and 2 for invalid evidence.

| Bundle field | Contents |
| --- | --- |
| `mode`, `complete_interval`, `account_ref` | `PAPER_ONLY`, true, and a local paper account alias |
| `before`, `after` | Complete position maps in `positions` keyed by symbol, trade-date `cash`, `observed_at`, `account_ref`, and `currency` set to `USD` |
| `orders` | One object per order with `report`, `intents`, and `paper_order_snapshot`. The broker snapshot needs `submitted_at` and `updated_at`. |
| `fills` | The normalized individual fill records documented above, with activity IDs unique across the account |
| `cash_movements` | Non-trade ledger records with `movement_id`, `account_ref`, `currency`, `occurred_at`, and signed decimal-string `amount` |

Include only orders submitted after the opening snapshot and obtain the
ending order and balance records for the same cutoff. The cash movements
may include deposits or withdrawals. Fill costs and fees are already
accounted for by the tool. Use consistent trade-date cash and complete
position snapshots so a symbol missing from the map can be treated as zero.
The tool surfaces unexplained position changes, cash differences, missing
fills, and order discrepancies. Settlement, fill corrections, sell orders,
and other position adjustments are outside this replay contract. The
bundle's completeness and provenance require independent confirmation.
