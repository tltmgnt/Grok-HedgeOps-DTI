# Phase 12 — Security enforcement boundary

The `hedgeops.workflow.record_review` function now requires a valid operator
token at the **domain write boundary**. Calling it directly, rather than
through `operator_cli.py`, no longer bypasses the token check.

Set `HEDGEOPS_OPERATOR_TOKEN` to a randomly generated secret of at least 24
characters before using the review CLI or `integrated_demo.py`.
Never commit this token. Tests supply synthetic tokens only.

## Threat model and limitations

- This is **shared-secret authorization**, not individual identity
  authentication, MFA or RBAC.
- Any process with the secret can approve; a reviewer label is self-reported.
- Direct SQLite writes can bypass Python application controls.
- Other state mutations (case creation, measurements and prediction tracking)
  are not protected by this operator secret.
- The `authorized_review` compatibility wrapper can accept a configured
  token override for test purposes, but the domain write still checks the
  environment-configured secret.
- No signature, external audit anchor, encrypted database, key rotation,
  network security layer or production identity provider is implemented.

## Validation

```bash
python release_check.py --verbose
```

New regression tests verify missing, wrong and valid tokens at the domain
boundary, and fail-closed behavior when no token is configured.

This is an incremental security hardening step, **not** production certification.
