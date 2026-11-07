# Purchase and analyze a paper decision at any time

The screenshot's green scheduled run was a synthetic demo. Its skipped purchase
jobs were expected: a schedule carries no manual action, symbol or purchase amount.
The previous `purchase_now` command only created a pending human-review request.
This patch adds `paper_purchase_decision.py` and connects it to the workflow.
The existing `purchase_now.py` and `alpaca_purchase.py` remain compatible.

## GitHub actions

After this patch is merged, open **Actions → Paper Purchases and Decision Analysis
→ Run workflow** on `main`.

| Action | Result |
|---|---|
| `alpaca_paper_buy` (default) | Record the decision first, then attempt a real Alpaca **paper** order |
| `purchase_now` | Record/analyze the decision without credentials; optional reference-price simulation |
| `reconcile_paper_order` | Read an existing order using its original request ID; never POST |
| `simulate` | Run the separate synthetic $200 demo; no purchase order |

Enter the uppercase ticker, $1–$200 amount in whole cents, your hypothesis and an
exit/evaluation rule. SPY and $10 are form defaults, not recommendations.
The optional reference price creates a hypothetical quantity, explicitly separate
from any broker fill. Without a price or credentials, the decision is recorded
with unknown market data, not a fabricated execution.

The analysis job has **no broker environment approval or credential dependency**.
It writes its artifact before the broker job can wait for approval or fail.
It retains your hypothesis, observations, assumptions, risks, unknowns, reference
mark, timestamp and decision ID. It is deterministic research, not an LLM-generated
valuation or a prediction of profitable returns.

The broker job uses the existing `broker-purchase-approval` GitHub environment.
Set dedicated `ALPACA_PAPER_API_KEY` and `ALPACA_PAPER_API_SECRET` there (or at the
repository level). Existing `ALPACA_API_KEY` / `ALPACA_API_SECRET` names are supported
as a compatibility fallback. Only the fixed paper host is contacted; a live key
does not enable live trading. Keep environment protections consistent with your
intended manual approval process. This patch does not bypass required reviewers.

Manual decisions do not require the automatic strategy's momentum/news gates,
daily attempt limit, five-position cap, or an open-market clock. Broker account
eligibility, available paper cash, asset support and $200 request bounds still apply.
This lets you research user-chosen trades even when the automatic strategy skips.

An order can be accepted/queued while the market is closed. Immediate execution
and a fill are not guaranteed; broker outages, restrictions, unsupported tickers,
and missing credentials cannot be overridden by a workflow. No extended-hours
or overnight execution is requested. Do not call a queued order filled.

## Re-runs and reconciliation

The default ID is `hedgeops-GITHUB_RUN_ID`; rerunning the same workflow keeps it.
The code looks up this ID before submitting, validates the ticker/amount match,
and returns the existing order rather than buying twice. A new workflow dispatch
is a new paper decision unless you explicitly supply the previous ID.

After a timeout or unconfirmed submission, choose `reconcile_paper_order`, supply
that original ID, ticker and amount. This only performs GET requests. Do not create
a new request ID to resolve an ambiguous purchase. Rejected/canceled/expired
orders are shown as terminated; an existing ID is never silently reissued.

Broker results distinguish accepted/pending, filled, terminated and unconfirmed.
Fill quantity, average fill price and fill timestamp are retained when the broker
provides them. Later outcomes are not automatically inferred from the initial
acknowledgment. Use reconciliation to refresh them.

Artifacts are retained for 90 days; download before expiry. These are per-decision
records, not a cash-account ledger or automatic long-horizon attribution engine.
The repository is public: do not put sensitive personal information in the thesis
or other workflow inputs/artifacts. No API credentials are written into artifacts.
The final workflow summary explains that scheduled demo success is not purchase success.

## Local commands

No dependencies beyond Python's standard library are needed by this command.

```sh
# Always-available reference simulation; no credentials and no broker order.
python paper_purchase_decision.py --symbol SPY --notional 10 \
  --reference-price 500 --request-id paper-experiment-001 \
  --thesis 'Illustrative test; evaluate after five sessions' \
  --output-dir data/purchase-001

# With securely configured dedicated paper credentials:
python paper_purchase_decision.py --symbol SPY --notional 10 \
  --request-id paper-experiment-002 --submit-paper \
  --output-dir data/purchase-002

# Refresh the actual broker outcome without placing another order:
python paper_purchase_decision.py --symbol SPY --notional 10 \
  --request-id paper-experiment-002 --reconcile-only \
  --output-dir data/purchase-002-reconciled
```

The first command's $500 reference price is an arbitrary example, not a quote.
Reference simulations assume immediate full allocation and exclude fees/slippage.
They cannot validate real execution quality or prove that a trend is profitable.

Alpaca reference: https://docs.alpaca.markets/us/docs/orders-at-alpaca .
