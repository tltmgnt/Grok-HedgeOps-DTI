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
