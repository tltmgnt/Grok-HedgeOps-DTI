# Paper research agent

The **Paper Research Agent** workflow runs the existing bounded paper strategy
through an auditable process. It is an autonomous controller with an optional Grok
critic, not a model with unrestricted broker tools. Strategy version remains
`momentum-news-v1`; agent/process version is `paper-agent-v1`.

## Process

1. **Plan:** record the fixed paper policy and the run's research objective.
2. **Observe:** check the broker clock, account-wide performance, data and existing
   positions/orders. Closed-market sessions still reconcile previous outcomes.
3. **Research:** find an eligible candidate using the current deterministic scanner.
   Attach hashed source IDs to its daily-bar metrics, timestamped quote, and headlines.
4. **Challenge:** ask Grok to state the hypothesis, assumptions, counterargument,
   unknowns, invalidation and PASS/DEFER/REJECT verdict. Validate the response schema
   and every evidence citation. A PASS is permission to test a paper hypothesis,
   not a profitable-return forecast or a recommendation to use real money.
5. **Gate and execute:** DEFER/REJECT prevents a new entry. PASS goes through the
   existing executor's independent checks again. The model cannot change the symbol,
   notional, broker host, thresholds or daily limits. Risk exits remain deterministic
   and independent of AI availability. Manual purchase tools remain separate.
6. **Reconcile:** distinguish accepted/pending orders from full fills. Count only
   fully filled, exact-quantity strategy round trips; exclude mixed/manual holdings.
7. **Evaluate and report:** retain wins, losses, pending orders, missing records and
   limitations. Keep the policy fixed; evaluate future unseen sessions and a matched
   benchmark before reviewing a separately versioned change. No self-modifying code,
   parameter changes, or automatic transition to live money.

## AI configuration

The existing workflow now calls `paper_research_agent.py`. It uses the same
`paper-trading` environment and the same dedicated/legacy Alpaca paper secret names.
Add `XAI_API_KEY` as a repository or `paper-trading` environment secret for Grok.
Do not put the key into a variable, source code or workflow input.

An optional `XAI_MODEL` repository/environment variable selects an entitled text
model. The agent first checks the key's `/v1/models` response. If no model is set,
it selects an available `grok-4.3`, then `grok-4.7` or `grok-4.6`, in that order.
Unrecognized/unauthorized model configurations are recorded as unavailable.
A successful model-list check verifies configuration, not a completed inference.
The first eligible market-hours candidate triggers the real review call.

| `PAPER_AGENT_REVIEW_MODE` | Behavior |
|---|---|
| `auto` (default) | Use Grok when a key is configured; otherwise label the review deterministic and preserve the prior bounded paper strategy |
| `required` | No new automated entry unless a configured Grok review returns valid PASS |
| `off` | Explicitly use the deterministic process without AI calls |

When a key exists but the API/model is unavailable, the agent defers new entries;
it does not silently replace a failed AI review with approval. API timeouts,
truncated responses, extra order fields, fabricated source IDs and malformed JSON
also defer entries. Each run permits at most one model inference, with a 25-second
SDK timeout, zero SDK retries, no model tools/search and a 1,200-output-token cap.
There is no fixed monthly dollar cap here: xAI API usage is separately metered.
Use the provider's billing controls for an account-level spending limit.

The model receives only the candidate's supplied market evidence and fixed policy,
not credentials, account IDs, balances or your full holdings. Headlines are untrusted
input. The agent does not grant the model filesystem, network or execution tools.
Schema and provenance checks reduce errors; they do not prove that model claims
are true. Verified company fundamentals and causal valuation remain missing.

## Outputs

Each run adds these files to the existing 90-day evidence artifact:

- `agent-events.jsonl`: timestamped stages, policy, evidence, review and execution
  results in a hash-linked journal, written before any reviewed entry proceeds.
- `agent-report.json`: AI configuration status, inference call count, paper outcome
  counts, realized paper P/L and the journal's final integrity hash.
- `session.json`, `entry/decision.json`, `exit-intents.jsonl` (when applicable): the
  existing broker reconciliation and execution records.
- `summary.md`: readable process status in the Actions run summary.

The journal detects altered records within a run; it is not an external immutable
ledger or a signature by a trusted third party. Use a fresh output directory for
each run. Download artifacts before expiry. Brokerage history provides the
cross-run reconciliation source; no conversational AI memory is required.

Realized P/L uses confirmed fill quantity × (exit fill price − entry fill price).
It excludes fees and mixed/manual lots, and does not compute benchmark alpha,
cash-flow-adjusted portfolio returns or slippage against signal time. An unmatched
or malformed fill is incomplete, not a successful trade. No unseen-session results
are available merely because the agent was deployed.

The existing cash, daily commitment, five-position and quote guards are unchanged:
$10 entries, $100 daily buy cap, $100 post-order cash reserve, -3%/+6%/five-calendar-day
exit experiment. These are unvalidated experiment settings, not optimized limits.
The same enable flag and kill switch still apply to future submissions.

## Running it

**Actions → Paper Research Agent → Run workflow** defaults to a read-only rehearsal.
Scheduled weekday runs keep the previous half-hour cadence and consult the broker
clock. Push-triggered preflights are read-only. Closed markets produce no entries.
Actions schedules can be delayed; this is not a continuous streaming service.

Locally, with secure environment credentials and the existing paper settings:

```sh
python paper_research_agent.py --monitor-only --output-dir data/agent-rehearsal-001
# Omit --monitor-only only for authorized PAPER execution.
```

`paper_research_worker.py` now uses this agent for its optional 60-second polling
loop, retains a separate output directory per run, and stops on errors. Deploy only
one execution worker and disable the Actions scheduler while it runs externally.
A hosted runtime and streaming feed are not provisioned by this code change.

The separate **Paper Purchases and Decision Analysis** workflow still allows your
manual paper decisions. It does not acquire an AI veto or lose its always-available
reference-simulation path because of this agent.

API references: https://docs.x.ai/developers/model-capabilities/text/structured-outputs
and https://docs.x.ai/developers/model-capabilities/legacy/chat-completions .

## On-demand current market information

**Actions → Live Market Information → Run workflow** retrieves a read-only snapshot
for the specified symbol using the existing `paper-trading` credentials. It does
not submit orders or read balances/holdings. Download the timestamped JSON artifact.
Locally, run `python live_market_information.py --symbol SPY` with secure environment
credentials. No additional Python dependencies are required for this command.

The result includes broker market-open status, next open/close, quote timestamp,
observation time, quote age, bid/ask, source and feed coverage. Quotes older than
120 seconds, future timestamps and spreads over 0.5% are unavailable, never current.
IEX is single-exchange coverage; SIP is consolidated and requires entitlement.
The chosen feed is explicit; the command never silently falls back to another feed.
The existing paper entry and exit paths use the same quote guard when required by
the paper experiment. The headline gate now independently rejects missing, malformed,
timezone-free, future and older-than-seven-day publication timestamps instead of
trusting only the provider's date filter. Headlines remain unverified claims.

This is an on-demand REST snapshot, not continuous streaming or a guarantee of
correct information. Its timestamp describes that observation only. For ongoing
paper sessions use the existing worker with a minimum 60-second polling interval
and a hosted runtime; disable the Actions scheduler before deploying one worker.
The manual snapshot workflow does not start that worker or enable trading. Existing
paper limits, live-buy approval, credentials and kill switches still govern orders.
