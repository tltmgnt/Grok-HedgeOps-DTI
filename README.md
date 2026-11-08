# DTI Ω × HedgeOps Ω

Experimental temporal intelligence and strategic hedge-operations decision-support framework.

## Publication boundary

This is a public Apache-2.0 repository. Dependency hardening and code-owner routing
protect aspects of change integrity; they do not make the published implementation
confidential. Keep proprietary material outside this repository. See the
[IP boundary and remaining GitHub administration](docs/IP_BOUNDARY.md) and
[security reporting policy](SECURITY.md). Ω-R3B conformance remains unverified until
its original specification is supplied and mapped to implemented controls.

## Status

**v0.1 prototype:** one Grok-powered analysis agent. Multi-agent orchestration, arbitration, verification feedback, and autonomous execution are **not implemented yet**.

## Review and research options

Choose a path for [independent prototype review, comparative research, or operational validation](docs/REVIEW_AND_RESEARCH_OPTIONS.md). The guide defines the evidence required for each objective, records the scope of the initial offline review, and provides a submission checklist. These paths are plans, not completed certifications.

## Quick start

Requires Python 3.10+ and an xAI API account with API credits (separate from SuperGrok).

```bash
git clone https://github.com/tltmgnt/Grok-HedgeOps-DTI.git
cd Grok-HedgeOps-DTI
python -m venv .venv
source .venv/bin/activate
pip install --require-hashes --only-binary=:all: -r requirements.txt
cp .env.example .env
```

On Windows, activate with `.venv\\Scripts\\activate` and copy with `copy .env.example .env`.

Edit `.env` with your own `XAI_API_KEY` and an `XAI_MODEL` ID available to your xAI team. **Never commit your .env or share an API key.**

```bash
python agent.py "Evaluate the risks and timing of launching a new product."
```

The agent requests a JSON report with observations, evidence, assumptions, gaps, options, risks, recommendations and verification conditions. JSON parsing is implemented, but model output is not yet schema-validated; malformed responses may fail. Outputs are hypotheses, not verified facts.

## Purchase Now — manual paper request

GitHub Actions → **Offline Paper Trading** → **Run workflow** → choose `purchase_now`, enter an uppercase `symbol` and `notional_usd` (up to $200). Download the `purchase-now-paper-request` JSON artifact to review the proposed purchase intent. Run `simulate` instead to execute the existing offline synthetic-price simulation.

The generic `purchase_now` choice creates a **pending human-review request only**. It does **not** buy securities, submit a simulated broker order, check quotes or balances, connect to exchanges, or act on a trading signal. No broker credentials are used. For CLI use: `python purchase_now.py --symbol SPY --notional 25 --output purchase-request.json`. See [paper-trading documentation](docs/PAPER_TRADING.md).

## Broker connectivity and live Purchase Now

The Actions workflow now has separate `alpaca_paper_buy` and `alpaca_live_buy` options. The Alpaca adapter uses the official account, asset and order REST endpoints. It checks the account is active, unblocked, has sufficient cash and buying power, and that the symbol is tradable and supports fractional notional orders. It submits a **market buy** of $1–$200 using a client order ID; this is a real order when `alpaca_live_buy` is selected. Market orders can fill at unexpected prices and may be rejected or unfilled.

**Before using live mode:** configure GitHub Actions environment `broker-purchase-approval` with required human reviewers and deployment-branch restrictions, then provision `ALPACA_API_KEY` and `ALPACA_API_SECRET` as environment secrets, and set the protected environment variable `ALPACA_LIVE_TRADING_ENABLED=true` to opt in. Live mode additionally requires the exact manual workflow input `I AUTHORIZE LIVE BUY`. **Never** use production credentials for paper mode or share secrets in issues or logs. Configure and test this environment yourself; the repository cannot configure your brokerage or GitHub approval settings. Review order status directly in Alpaca after submission, especially if a workflow fails or times out. A workflow retry may create another order, so avoid retries until reconciled.

Other requested brokers are tracked in `broker_connectivity.py` with explicit fail-closed status: Webull (official trading API; approved account/key required), Webull Pay (separate crypto trading API), IBKR (official API with authentication/session requirements), and Merrill (no verified public retail order-submission API). **None of these four routes currently submits live orders.** No undocumented endpoint or screen-scraping workaround is used. See [broker integration plan](docs/trading-platform-integration.md).

## Position-loss monitoring (read-only)

A separate **Read-only Position Loss Monitor** GitHub Actions workflow monitors Alpaca account positions and flags unrealized losses against broker-reported cost basis. Defaults: warning at **5%**, critical at **10%**. These are illustrative alert thresholds, **not** automatic stop-loss orders. The monitor never submits, cancels or modifies broker orders.

To configure, create the GitHub Actions environment `broker-monitoring`, restrict deployment branches to `main`, and add **dedicated read-only-capable** account credentials as environment secrets `MONITOR_ALPACA_API_KEY` and `MONITOR_ALPACA_API_SECRET`. Broker API key permissions vary; do not assume a key is read-only unless your broker enforces that permission. Optionally set `HEDGEOPS_ALERT_WEBHOOK` to a **private** HTTPS notification endpoint accepting a JSON `text` field. The webhook sends symbol and loss percentages; protect it as sensitive. For scheduled monitoring, `MONITOR_SCHEDULE_MODE` defaults to `paper`; set it to `live` only after you have explicitly chosen to monitor a live account with appropriate credentials. Scheduled checks run every 30 minutes on weekdays during a broad UTC market-hours window, including times when markets may be closed. They can be delayed or skipped. Manual dispatch allows paper/live selection and threshold inputs.

The job writes a detailed JSON report only to its temporary runner filesystem; it **does not upload account holdings as a public artifact**. The job summary contains only alert counts. If secrets are not configured, the scheduled job skips monitoring. The repository cannot protect an account if the job does not run, the API fails, quotes are stale, or alerts are not delivered. Broker-native protective orders may be more appropriate for time-critical risk management, but even these do not guarantee a sale at the stop price.

Run locally with your own environment variables:

```bash
python position_loss_monitor.py --mode paper --warning-pct 5 --critical-pct 10
```

Review [monitoring and protection guide](docs/POSITION_LOSS_MONITORING.md) before connecting any account.

## Planned architecture

Orchestrator Ω → Temporal / Capacity / Strategy / Risk / Hedge / Contrarian / Red-Team agents → Evidence-based Arbitrator Ω → Human-approved decision → Observation and feedback.

Proposed state: `S_t = (T, C, O, U, R, G, V)`, representing time, capacity, options, uncertainty, risk, gaps and verification.

## Roadmap

1. Validate single-agent structured output with JSON Schema and tests.
2. Add sourced retrieval and evidence provenance.
3. Implement five-agent HEDGE 302 laboratory.
4. Add conflict arbitration and human approval gates.
5. Track predictions, falsification tests, and observed outcomes.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Autonomous paper sessions

See [the paper experiment runbook](docs/AUTONOMOUS_PAPER_SESSIONS.md) for
dedicated paper credentials, scheduled runs, the kill switch, fixed entry/exit
rules, current-data quote checks, optional persistent worker, and evaluation limits.
Scheduled paper execution is enabled by default after merging this version unless
repository/environment variables disable it. Real-money execution is not enabled.

For manual choices, see [paper purchases and decision analysis](docs/MANUAL_PAPER_PURCHASES.md).
The manual workflow records analysis before broker approval/submission; it supports
reference simulations and read-only reconciliation without claiming queued orders are fills.

The [Paper Research Agent](docs/PAPER_RESEARCH_AGENT.md) adds a complete process:
plan, observe, research, AI challenge, deterministic risk checks, paper execution,
fill reconciliation and outcome evaluation. Configure `XAI_API_KEY` for Grok review;
its absence is explicitly labeled as deterministic mode, never as AI analysis.

Dependency inputs and generated hash locks are described in [the maintenance policy](requirements-policy.md). CI uses `requirements-dev.txt`; production uses `requirements.txt`.

## ResearchOS / TECT concept integration

The [ResearchOS / Topological Epistemic Control Theory technical concept paper](docs/researchos/TECT_WHITE_PAPER.md) proposes an epistemic control and assurance infrastructure for AI-generated knowledge. Read the [repository integration status](docs/researchos/INTEGRATION.md) and [machine-readable scope](docs/researchos/integration.json) for the boundary between the concept and implemented capabilities. Performance targets are research objectives, not achieved results. This documentation addition does not implement the complete ResearchOS architecture or change operational authority.
