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
- `PAPER_REGIME_APPROVED_SHA256`: 64-character lowercase SHA-256 digest of
  the **exact evidence file bytes**, independently reviewed and pinned through
  protected configuration (not computed from that file by the trading job).
- `PAPER_REGIME_APPROVAL_EXPIRES_AT`: timezone-aware ISO 8601 expiry of the
  approved evidence, at most 24 hours ahead of the current check.

- `PAPER_REGIME_APPROVAL_HMAC_KEY`: protected, randomly generated 32–64 byte
  key expressed as lowercase hexadecimal; never commit or log it.
- `PAPER_REGIME_APPROVAL_HMAC_SHA256`: lowercase HMAC-SHA256 of the
  domain-separated, versioned approval message described below. This
  authenticator must be issued by a separate reviewed process, never
  derived dynamically by the execution workflow.

The signed bytes are the UTF-8/ASCII concatenation of:
`HEDGEOPS:PAPER:REGIME_ENTRY:v1`, newline,
`regime-prototype-v1`, newline,
`PAPER_REGIME_APPROVED_SHA256`, newline,
`PAPER_REGIME_APPROVAL_EXPIRES_AT` (exact text). Use HMAC-SHA256.
Changing the policy version, expiration text, or evidence digest invalidates
the authenticator. Evidence classification is independently re-evaluated at
each gate check; the HMAC must never substitute for those checks.

When the optional gate is active, both the protected digest and expiry are
**mandatory**. A byte change, missing value, invalid digest, expired approval,
or observation older than 36 hours blocks new buys. The digest is checked
again immediately before an automatic broker POST. Avoid storing approved
hashes in public repository files. Restrict who can change protected settings,
review independent source provenance, and revoke approvals promptly.

**Security limitation:** The SHA-256 pin detects file changes, while
HMAC-SHA256 checks whether the approval token was created with the shared
secret. HMAC is **not a public-key digital signature** and does not prove
reviewer identity, market-data provenance, or data correctness. In particular,
the verifier runtime necessarily has the shared secret: a compromised runner,
or a maintainer permitted to change both its secret and evidence, can forge
approval. Use protected environments, separation of duties, private key
rotation/revocation processes, and independent market-data/strategy review.
Do not confuse a valid token with trading authorization, independently
validated alpha, or a safe time to trade. The control remains disabled until
explicitly authorized.

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
blocked entries before any POST, missing/forged HMAC approval, changed
digest or expiry, stale and conflicting evidence, separate read-only reconciliation
and continuing exit management. This gate does not
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
