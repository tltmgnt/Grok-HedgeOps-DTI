# Optional PAPER regime entry control: staged integration

**Status:** Draft, not enabled by default. This is a reviewed-gate integration
proposal, *not* proof of bull-market profitability or a safe execution
recommendation. PR #73 (decision table) and PR #74 (offline prototype)
must be reviewed and merged before this stacked change.

The shared `paper_regime_controls.entry_block_reason` runs before *new*
PAPER buy submissions. Automated assessments skip before broker queries,
and automated execution rechecks just before POST. Manual CLI orders are
screened before reserving a local replay marker, and `submit()` rechecks
before POST. Existing-order lookup remains available for reconciliation,
and exit sells are not gated.

## Activation and controls

This is intentionally **opt-in** to avoid unreviewed operational changes.

- `PAPER_REGIME_CONTROL_ENABLED=true`: activates the entry block gate;
  unset/false retains existing behavior for staged rollout.
- `PAPER_REGIME_REVIEW_APPROVED=true`: a second explicit approval flag.
  The flag is not a signature or independent security boundary.
- `PAPER_REGIME_EVIDENCE_FILE`: local read-only JSON evidence record.

Example synthetic evidence shape (NOT a validated production decision):

```json
{
  "decision_at": "2026-11-10T20:00:00Z",
  "observed_at": "2026-11-10T19:00:00Z",
  "source_id": "INDEPENDENT-REVIEW-REFERENCE",
  "evidence_verified": true,
  "trend_pct": 3.0,
  "breadth_fraction": 0.65,
  "realized_vol_pct": 15.0
}
```

The prototype classifier uses **illustrative, non-calibrated thresholds**.
It cannot verify the source ID, rights, independence, or signature of a
supplied file. The approval flag is only a workflow assertion. Therefore
**do not activate for real broker submissions without independent data,
risk and authorization review**. No PAPER or live execution has been
authorized by this change.

When activated, the control blocks unknown/unverified, neutral, bear,
stale, future or conflicting evidence. It considers only a fresh, explicitly
reviewed BULL label as eligible to **continue through the existing checks**.
BULL is never a buy instruction: all broker, risk, kill-switch, market
clock, ledger, and explicit approval requirements remain necessary.

## Tests

```sh
python -m unittest discover -s tests -p 'test_paper_regime_controls.py' -v
```

The tests use local synthetic JSON and mocked broker calls. They cover
blocked entries before any POST, review/freshness requirements, separate
read-only reconciliation and continuing exit management. This gate does not
address direct broker API access outside these entry paths or confer
transactional authorization.

## Rollout

1. Keep the new control inactive while validating historical regime
   classification and independent evidence provenance.
2. Review PR #73, PR #74, and this draft; pass offline and integration CI.
3. Require an explicit operational change review and protected environment
   settings before activation. Activate initially only in a non-executing
   rehearsal and examine skip reasons.
4. Preserve current kill switches and disable execution whenever the
   regime evidence is unavailable or any approval is withdrawn.

**This is not guaranteed protection against crashes, gaps, or losses.**
