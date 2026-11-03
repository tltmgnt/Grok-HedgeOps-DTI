# Phase 10 — Release Validation Ω

## Offline release check

```bash
python release_check.py --verbose
```

This compiles Python modules and runs all discovered offline unit tests. The
GitHub Actions workflow also runs this command on Python 3.10 and 3.12.

## Required release evidence

1. Latest pull-request CI must complete successfully on both Python versions.
2. A maintainer must inspect test logs and review the entire pull-request diff.
3. Live xAI API integration must be manually tested using an authorized key,
   supported model and a controlled spending limit.
4. Security review must address unauthenticated lower-level approval functions,
   unencrypted case data, operator secret management and source provenance.
5. Recovery and concurrency tests must be extended to concurrent processes.
6. Explicit maintainer sign-off is required before marking the PR ready.

## Decision

**Not production-ready.** This phase provides reproducible offline validation,
not production certification. No automated trading or external execution exists.
