# Incremental HedgeOpsTeam integration

This repository keeps the offline `hedgeops_team` package separate from broker, network, and order interfaces.

## Increment 1: Safety foundation
- Require explicit equity, cash, exposure, and drawdown fields; never silently default missing risk information.
- Reject non-finite or non-positive forecast and realized prices and unsupported forecast actions.
- Normalize timezone-aware ISO timestamps to UTC; reject mixed aware/naive comparisons.
- Optionally enforce exact bar cadence using `HedgeOpsTeam(expected_bar_interval=timedelta(days=1))`; the default remains chronology-only.
- Label SELL as a directional signal only; never interpret it as an executable order quantity.
- Preserve `paper_only=True` and existing default behavior for valid inputs.

Run `python -m pytest tests/ -q` and `python release_check.py --verbose`.

## Future increments (separate PRs)
1. Provenance and evidence independence.
2. Offline walk-forward baselines and calibration.
3. Statistical robustness.
4. Research manifests and governance where justified by actual use.

No trading or broker execution is enabled by this increment.
