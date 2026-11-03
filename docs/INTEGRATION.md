# Phase 6 — Integrated Intelligence Ω

## Workflow

1. `create_case(store, problem, ask)`: create a case, run five agents, persist
   their reports and arbitration outcome.
2. `record_review(...)`: a human records an explicit decision, identity label
   and rationale. No action execution is authorized.
3. `propose_prediction(...)`: allowed only after `approved_for_tracking`.
4. `record_measurement(...)`: store a reviewer-supplied measurement and its
   source label; compute a simple target tolerance check.
5. `replay(store, case_id)`: reconstruct the case state from persisted events.

## Offline demonstration

```bash
python integrated_demo.py
python -m unittest discover -s tests -v
```

The demo uses simulated agents, synthetic measurements and a synthetic reviewer.
The underlying workflow accepts the existing Grok-backed `ask` function, but
the `lab.py` CLI is not yet automatically wired into persistent case creation.

## Safety and limitations

- Approval is a recorded reviewer label, **not authenticated identity**.
- Approval only permits prediction tracking, not trading or deployment.
- There is no user interface, external action execution, automated source
  verification or statistical causal inference.
- SQLite history is durable locally but not tamper-proof or encrypted.
- Replay reconstructs known workflow event types. It is not a general-purpose
  agent memory or model-training mechanism.
- Errors during agent calls may leave a created case without an analysis; this
  can be inspected via event history but requires an explicit recovery strategy.

Next: wire the live Grok CLI into the workflow, add authenticated review and
observability, transactional concurrency controls and integration tests.
