# DTI Ω × HedgeOps Ω

Experimental temporal intelligence and strategic hedge-operations decision-support framework.

## Status

**v0.1 prototype:** one Grok-powered analysis agent. Multi-agent orchestration, arbitration, verification feedback, and autonomous execution are **not implemented yet**.

## Quick start

Requires Python 3.10+ and an xAI API account with API credits (separate from SuperGrok).

```bash
git clone https://github.com/tltmgnt/Grok-HedgeOps-DTI.git
cd Grok-HedgeOps-DTI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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

**Before using live mode:** configure GitHub Actions environment `broker-purchase-approval` with required human reviewers and deployment-branch restrictions, then provision `ALPACA_API_KEY` and `ALPACA_API_SECRET` as environment secrets. Live mode additionally requires the exact manual workflow input `I AUTHORIZE LIVE BUY`. **Never** use production credentials for paper mode or share secrets in issues or logs. Configure and test this environment yourself; the repository cannot configure your brokerage or GitHub approval settings. Review order status directly in Alpaca after submission, especially if a workflow fails or times out. A workflow retry may create another order, so avoid retries until reconciled.

Other requested brokers are tracked in `broker_connectivity.py` with explicit fail-closed status: Webull (official trading API; approved account/key required), Webull Pay (separate crypto trading API), IBKR (official API with authentication/session requirements), and Merrill (no verified public retail order-submission API). **None of these four routes currently submits live orders.** No undocumented endpoint or screen-scraping workaround is used. See [broker integration plan](docs/trading-platform-integration.md).

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
