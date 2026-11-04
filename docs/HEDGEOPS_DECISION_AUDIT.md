# Increment 2: decision provenance and auditability

This increment is stacked on the Increment 1 safety branch.

## What is recorded
- Deterministic input snapshot and SHA-256 digest.
- Explicit risk limits, optional bar interval, independent-strategy requirement, and strategy-source classification.
- Complete paper-only decision snapshot, evidence and reason codes.
- Schema and caller-supplied implementation identifier.
- Aggregate audit digest over all recorded fields.

## Validation
```bash
python -m pytest tests/ -q
python release_check.py --verbose
```

## Trust boundary
A SHA-256 digest detects accidental or unauthorized changes only when the expected digest is held separately. It is **not** a digital signature or proof of authorship. An attacker who can rewrite the entire audit can recompute the digests. For independent assurance, use authenticated storage or signatures in a later increment.

The default strategic action mirrors the temporal action and is labeled `unverified_mirror`, **not independent confirmation**. `require_independent_strategy=True` fails closed to HOLD unless a separate adapter is supplied. An adapter's presence does not prove genuine independence; that requires separate governance.

Injected adapters receive defensive copies of the input. Replay verification requires a deterministic adapter and matching policy.

No broker, order, or live-trading interfaces are added.
