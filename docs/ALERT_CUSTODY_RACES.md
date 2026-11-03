# Phase 42 — Race-aware alert custody checks

Phase 42 adds two custody observations around critical alert-journal operations:

1. **Publication:** after a successful atomic compare-and-swap, read the
   custody record again. If its sequence/fingerprint differs from the
   published record, raise `AlertCustodyError` instead of returning a
   checkpoint that may already be stale.
2. **Verification:** after checking the authenticated checkpoint and journal
   ancestry, read custody again. Reject an observed advance, deletion or
   substitution that happened while the journal was being checked.

Both checks retain the fail-closed behavior of Phases 39–41. The new tests
simulate concurrent advances, CAS conflicts, missing custody and malformed
follow-up reads. No credentials or journal payloads enter custody records.

**Consistency boundary:** These are *double-read consistency checks*, not
a lock, transaction spanning the journal and remote custodian, or a
linearizable recovery decision. A custodian may advance immediately after
the final read; a malicious or rollbackable custodian can replay an old
record on both reads. Stronger guarantees require an independent trusted
custodian with atomic snapshot/lease or fencing-token semantics and
coordinated recovery. A successful CAS followed by failed confirmation
may still have committed; operators must re-read state rather than blindly
retrying publication.

Run `python release_check.py --verbose` and confirm both CI matrix jobs.
