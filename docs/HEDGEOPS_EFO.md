# Experience–Facts–Observation (EFO) framework

The EFO framework is a modern, practical interpretation of the experimental-science tradition associated with the Royal Society's founding on 28 November 1660. **It is not a historical quotation or a claim that the founders used this schema.**

## Workflow
1. Record an **experience** or **observation**, with source, observed time, recorded time, measurements, and a content digest.
2. Derive a **fact** linked to one or more observation/experience digests. A link is traceability, not proof that the claim is true.
3. Register a **hypothesis** with linked evidence.
4. Before the outcome horizon, register a **falsification test**: named metric, threshold, comparison, horizon.
5. After the horizon, record the observed value and compute **supported** or **falsified**. A test result is not a statistical significance test.
6. Export a deterministic, content-addressed bundle and verify its internal references and chronology.

## Offline example
```python
from hedgeops_team.efo import Observation, register_test, evaluate_test, export_chain, verify_export

obs = Observation("observation", "2026-11-01T00:00:00Z", "2026-11-01T01:00:00Z", "csv:fixture", "Close was 100", {"close": 100})
hyp = Observation("hypothesis", "2026-11-01T01:00:00Z", "2026-11-01T02:00:00Z", "researcher", "Close will exceed 101", {"target": 101}, (obs.digest,))
test = register_test(hyp, criterion="close", operator="gt", threshold=101, registered_at="2026-11-01T02:00:00Z", horizon_end="2026-11-02T00:00:00Z")
outcome = evaluate_test(test, outcome_at="2026-11-02T00:00:00Z", recorded_at="2026-11-02T01:00:00Z", source_id="csv:fixture", observed_value=102)
bundle = export_chain((obs, hyp), (test,), (outcome,))
assert verify_export(bundle)
```

## Boundaries
- **Paper-only**, no brokerage, execution, position sizing, or live-market access.
- SHA-256 is an integrity checksum, **not a signature**. A party that controls all records can rewrite the chain. No independent source authentication is implemented.
- Source IDs are user-supplied labels; they are not independently verified. An observation may be wrong or fabricated.
- Time fields are caller-supplied, not trusted timestamps. The framework validates ordering, not historical truth.
- Tests compare numeric outcomes to registered thresholds. No statistical inference, causal claim, or investment performance guarantee.
- All tests are standalone; EFO does **not** silently change HedgeOpsTeam decision policy.

Run `python -m pytest tests/test_hedgeops_efo.py -q` and the repository's full offline CI gate before merging.
