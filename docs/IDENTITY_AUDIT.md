# Phase 15 — Local reviewer identity and audit

`hedgeops.identity.ReviewerRegistry` accepts trusted reviewer IDs, roles
(`approver` or `reviewer`) and distinct 32-byte-or-longer secret keys.
Keys must be provisioned securely outside source control and outside SQLite.
Only `approver` identities can sign `approved_for_tracking` decisions.
A `reviewer` can sign rejection or revision requests.

`record_attested_review(...)` requires BOTH the existing operator token and
a reviewer-specific HMAC-SHA256 signature over the exact case ID, decision,
reviewer ID, rationale and versioned domain. The signed review is stored in
the existing hash-chained journal; the secret key is not stored.

`verify_case_review(store, case_id, registry)` checks the journal hash chain,
requires exactly one review event, and validates the signature and role.
Unsigned legacy reviews return false. Audit verification needs the trusted
registry and keys.

## Important boundaries

- This is a **local symmetric-key proof of possession**, not login, SSO,
  hardware-backed identity, public-key signature or non-repudiation.
- A registry administrator or anyone with a reviewer's key can impersonate
  that reviewer. Key rotation/revocation and trusted key distribution are not
  implemented.
- The original `record_review` API remains available for backward compatibility.
  It records **unsigned** reviews; existing `propose_prediction` does not
  require `verify_case_review`. Thus attested approvals are **opt-in**,
  not a production-enforced authorization boundary.
- Direct database access can bypass application authorization. The hash chain
  is not externally anchored, and SQLite data is not encrypted.
- No secrets should be committed, logged or included in case payloads.

## Offline tests

`python release_check.py --verbose`

The release evidence checklist must remain unapproved until the full
authorization design is independently reviewed and validated.
