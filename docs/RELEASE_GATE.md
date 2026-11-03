# Phase 11 — CI validation and fail-closed release gate

## Verified CI evidence

GitHub Actions run 41668253658 for Phase 10 commit
`2d49abc502ddbbd0cc4afd1a2bcf3067cff87451`
completed successfully. Both jobs, Python 3.10 and Python 3.12, succeeded.

This proves the offline workflow passed, not that live xAI integration or
production security has been validated.

## Release gate

```bash
python release_gate.py release_evidence.example.json
```

The example deliberately exits with status 1 because important requirements
are unverified. The gate requires six explicit boolean attestations:
offline CI, live provider test, authorization review, data protection review,
concurrency review, and maintainer approval.

**This is a self-reported checklist, not cryptographic proof or automatic
verification.** Anyone able to edit the evidence JSON can set all fields to
true. A successful result means only that all flags were supplied; it does
not merge, deploy, authenticate reviewers or certify security.

Do not mark unverified checks true. The project remains a draft release
candidate until real controls and independently reviewed evidence exist.
