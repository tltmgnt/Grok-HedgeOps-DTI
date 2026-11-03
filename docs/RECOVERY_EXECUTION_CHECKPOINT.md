Phase 52: Execution audit checkpoint.

The checkpoint signs the verified local execution audit head with HMAC-SHA256. Store trusted checkpoints independently of the local database. Verification permits later valid events but rejects truncation and divergence. HMAC does not establish freshness.
