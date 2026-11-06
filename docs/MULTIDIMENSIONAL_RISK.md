# Multidimensional risk diagnostics

The qualification workflow now evaluates twelve independently reported dimensions: market, liquidity, volatility, execution, portfolio, drawdown, data integrity, AI model, strategy, broker/API, operations, and event/gap risk.

Each dimension returns PASS, HARD, SOFT, or UNKNOWN, with a machine-readable code. Overall outcomes are REJECT (any HARD), DEFER (any UNKNOWN or zero-size soft gate), REDUCE_SIZE (soft threshold), or PASS. A hard gate can never be overridden by a soft size reduction. The existing deterministic qualification checks remain in force.

**Fail-closed change:** A candidate without explicit `kill_switch: false`, `grok_veto: false`, `event_within_24h: false`, `volatility_pct`, `estimated_slippage_bps`, `portfolio_exposure_pct`, and `daily_loss_pct` is deferred. A missing value is never silently interpreted as safe. A verified snapshot producer must provide these values. No market-data ingestion or broker execution is enabled by this PR.

The threshold values (volatility >4%, slippage >15 bps, portfolio exposure >20%, daily loss >1%, spread >20 bps) are **illustrative engineering defaults** that require validation. Some risk categories rely on snapshot fields and are not independently verified against Alpaca. This module is diagnostic and does not replace live broker reconciliation. Scheduled runs remain dry-run only.

To validate: `python -m unittest discover -s tests -p 'test_trade_qualification.py' -v`. CI results must be checked before merge.
