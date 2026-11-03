# Phase 74 — Transport diagnostics

Readiness distinguishes transport errors raised by custody reads from readable custody evidence that does not verify. Transport errors return `CUSTODY_TRANSPORT_UNAVAILABLE` and CLI exit `3`; evidence mismatch returns `CUSTODY_UNVERIFIED` and exit `2`. Neither permits recovery. Diagnostics omit raw errors and connection details.

Timeout and HTTP authentication-rejection regression tests assert the new classification. Malformed JSON and invalid ETags remain evidence-unverified responses. The observer never publishes custody.
