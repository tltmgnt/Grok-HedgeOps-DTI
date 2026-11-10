# Production trading readiness gates

Status: **NOT APPROVED FOR UNATTENDED LIVE TRADING**. This is an engineering acceptance plan, not an audit or claim of investment performance.

## Release invariants (all mandatory)

1. **Change governance:** protect `main` with pull-request review, required passing checks, no force pushes, restricted bypass, and verified CODEOWNERS routing. Capture GitHub settings evidence.
2. **Broker boundary:** paper and live credentials, endpoints and environments are distinct. Live mode requires an explicit manual authorization and protected environment approval. Never infer approval from a passing CI run.
3. **Fail closed:** reject new orders on stale/missing quotes, uncertain account or order state, exceeded risk limits, disabled kill switch, unavailable reconciliation, or unavailable audit persistence.
4. **Idempotency:** persist order intent and deterministic client order ID *before* submitting. On timeout or ambiguous response, query broker order state by client ID; never automatically repeat an uncertain POST.
5. **Reconciliation:** compare broker orders, fills, positions, buying power and cash against local ledger; block new orders on unresolved differences. Log timestamps and identifiers, redact credentials and sensitive account data.
6. **Recovery:** test process crash before POST, during POST, after broker acceptance, during fill, and after restart; demonstrate no duplicate exposure and an operator-visible incident.
7. **Alert delivery:** verify alerts reach a real receiver, failures escalate, and monitoring downtime is detectable. GitHub Actions schedules are not guaranteed execution or a substitute for broker-native risk controls.
8. **Controlled rollout:** offline simulation -> authenticated paper provider acceptance -> supervised limited live canary only after written human approval. Every stage requires rollback and kill-switch rehearsal.
9. **Performance evidence:** preserve immutable research inputs, timestamped market data, fees, slippage, corporate actions, out-of-sample evaluation, and comparisons to simple buy-and-hold benchmarks. No profitable-edge claim without independent reproduction.
10. **Release evidence:** link commit SHA, CI results, provider responses (redacted), recovery exercises, alert delivery receipts, approver identity, and date. A checklist without evidence does not pass.

## Required acceptance scenarios

| Scenario | Expected result |
| --- | --- |
| Quote missing or stale | No new order; explicit reason and alert |
| Broker API 429/5xx or timeout after POST | No blind retry; query by client order ID; hold if unresolved |
| Duplicate workflow dispatch | At most one accepted intent/order per idempotency key |
| Process restart after accepted order | Rebuild state from broker; no second order |
| Partial fill and cancel race | Correct filled quantity and remaining exposure |
| Broker/local position disagreement | Block new orders pending reconciliation |
| Cash or risk limit exceeded | Reject before order submission |
| Paper credential used against live endpoint | Hard reject |
| Kill switch engaged mid-run | No subsequent new orders; document handling of existing orders |
| Alert endpoint unavailable | Durable incident record and tested alternate escalation |
| Unreviewed change to main | Rejected by enforced GitHub rules |
| Manual live request without environment approval | No live order |

## Evidence register

For each gate record: **owner**, **commit**, **environment**, **test procedure**, **expected result**, **observed result**, **artifact link**, **reviewer**, **date**, and **pass/fail**. An absent artifact means **unverified**, not passed.

## Existing workflow run: 42728876000

GitHub reported `paper-trading` and `outcome` succeeded; `decision-analysis` and `alpaca-purchase` were skipped. The run's successful offline $200 simulation does **not** demonstrate authenticated Alpaca acceptance, live-order safeguards, fill reconciliation, or production recovery.

## Release decision

Keep live trading disabled unless all mandatory gates are evidenced and approved by a responsible human operator. This document does not change GitHub branch rules, broker settings, secrets, deployment approvals, or order execution behavior; those require separate implementation and verification.
