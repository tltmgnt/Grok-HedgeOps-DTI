# Evidence register and independent review gates

This read-only tool implements three separate evidence-completeness gates:
`trading_evidence`, `investor_fit` and `operational_assurance`. Every gate requires
an owner, scope, subject ID, criteria version, evidence and a separately named
reviewer. Passing means eligible for human review only. It never submits orders,
changes trading policy, determines suitability or issues certification.

## Usage

```sh
python assurance_register.py --template > private-register.json
python assurance_register.py private-register.json --evidence-root private/evidence
```

Keep the register and evidence outside public version control. Investor profiles,
account records and assessment reports can be sensitive. Use opaque subject IDs;
keep personal information in access-controlled artifacts. Reports omit artifact
paths and contents but contain scope packet hashes and gate results.

The template is deliberately incomplete. Populate `strategy_version` and each
gate's `owner`, `scope`, `subject_id` and `criteria_version`. Subject IDs identify
the strategy evaluation, specific investor assessment or deployment being reviewed.
Do not reuse an investor or deployment approval for a different subject.

Each evidence record has this shape:

```json
{
  "requirement": "protocol",
  "strategy_version": "momentum-news-v1",
  "subject_id": "evaluation-001",
  "observed_at": "2026-11-01T00:00:00Z",
  "expires_at": "2026-12-01T00:00:00Z",
  "path": "protocol.json",
  "sha256": "REPLACE_WITH_ACTUAL_SHA256"
}
```

Paths must resolve within the supplied evidence root, including symlink resolution.
Evidence must exist, match its SHA256, have an aware timestamp, not be future-dated
and remain unexpired. Requirements must be unique and match their gate. Invalid
records, missing requirements, blockers and missing scope metadata fail closed.
Evidence expiry is a review policy choice; the tool does not invent an appropriate
validity period. Pin strategy versions to immutable release identifiers in practice.

Run the checker to obtain the current `packet_sha256` for each gate. After an actual
review, the reviewer records:

```json
{
  "decision": "APPROVE_FOR_REVIEW",
  "reviewer": "reviewer-identity",
  "rationale": "Describe the scope, findings and limitations of the review",
  "packet_sha256": "COPY_THE_REVIEWED_PACKET_HASH",
  "reviewed_at": "2026-11-02T00:00:00Z",
  "expires_at": "2026-12-01T00:00:00Z"
}
```

The review must postdate observations and remain current. The packet binds all
gate fields except `review`, plus the strategy version. Changes to evidence,
blockers, ownership, subject or scope invalidate the prior review. Reviewer identity
must differ from owner. These are local declarations: there is no identity provider,
signature validation or tamper-proof history. An authenticated approval service and
append-only audit store remain deployment work. Hashes establish consistency, not
the truth, completeness or statistical quality of an artifact.

Exit codes: 0 means all three gates are eligible for human review; 1 means at least
one is incomplete; 2 means malformed register/input. Individual gate outcomes remain
separate. No gate borrows another gate's approval. `execution_authorized` and
`certification_issued` are always false. Do not wire exit code 0 directly to a live
execution permission or use it as a certificate.

## Required evidence topology

| Gate | Required evidence categories |
|---|---|
| Trading evidence | Protocol, data integrity, complete experiment registry, execution costs, independent evaluation, attribution, degradation policy |
| Investor fit | Investor profile, loss capacity, portfolio context, alternatives, conflicts and authority, ongoing review |
| Operational assurance | Assessment scope, execution ownership, service objectives, recovery, security, change governance, independent assessment |

Trading records should connect fixed hypotheses to point-in-time data, all attempted
configurations, cost assumptions, held-out results and reconciled net outcomes.
No favorable result guarantees future returns. Investor-fit evidence must connect
the particular investor's circumstances to portfolio risks, costs and alternatives;
a general strategy report cannot establish individual fit. Operational evidence must
name deployment boundaries, assessment criteria and the actual assessor; test-suite
success cannot substitute for observed uptime or an external attestation.

## Temporal workflow integration

| Horizon | Evidence production or refresh task |
|---|---|
| 1 second | Collect sequence integrity, data age and latency observations |
| 10 minutes | Compare heartbeat and expected runs; reconcile pending actions |
| 20 minutes | Age incidents and assign unresolved items |
| 30 minutes | Link decisions to shared snapshots and strategy versions |
| 40 minutes | Recheck uncertain order states and entry blocks |
| 50 minutes | Reconcile missing artifacts and unacknowledged alerts |
| 60 minutes | Consolidate service health and evidence completeness |
| Daily | Reconcile fills, costs, cash movements and missing records |
| Monthly | Produce attributed evaluation and review investor-profile changes |
| Quarterly | Review operating evidence, restore drills and scoped release decisions |

The checker consumes artifacts; it does not create a stream, provision a scheduler,
perform statistical research or contact investors. Connect existing reporting jobs
to a private evidence root and invoke this CLI at declared review cutoffs. It is
separate from the existing offline release gate, which checks a different scope.
No public Actions artifact or automated broker integration is added.

## Acceptance checks

Tests exercise complete review-only outcomes, independent gates, content tampering,
expiry, future observations, path traversal, symlink escape, mismatched strategy
and subject, changed review packets, duplicate requirements and self-review. Real
production acceptance additionally requires authenticated reviewers, controlled
artifact ingestion, private storage, audit retention and substantive expert review.

## Automatic schedule

The **Scheduled Evidence Gates** Actions workflow checks all three gates on each
cadence below. Times are UTC; these are current evidence snapshots, not retrospective
profit calculations or automatic approval renewals.

| Cadence | UTC trigger | Pacific time during November 2026 |
|---|---|---|
| Every 10 minutes | Every hour at 03 13 23 33 43 53 | Same minutes every hour |
| Daily | 23:13 every day | 3:13 pm PST |
| Monthly | 00:23 on the first calendar day | 4:23 pm PST on the preceding day |
| Quarterly | 00:43 on January April July October 1 | Preceding day at 4:43 pm PST or 5:43 pm PDT |

Monthly/quarterly labels identify review checkpoints; the checker evaluates evidence
at actual execution time. GitHub may delay or skip schedules. No trading-calendar
or report-generation promise is implied. Manual dispatch is also supported. Schedules
start only when the workflow is on the default branch and Actions permits runs.

### Private evidence configuration

Set the repository Actions secret `ASSURANCE_EVIDENCE_BUNDLE_JSON` to a compact JSON
object containing `register` and `artifacts`. `register` is the existing complete
register; `artifacts` maps relative evidence paths to base64-encoded bytes:

```json
{"register": {"schema_version": 1, "strategy_version": "...", "gates": {}},
 "artifacts": {"protocol.json": "BASE64_OF_ACTUAL_ARTIFACT_BYTES"}}
```

This illustration is intentionally incomplete and will fail validation. Populate all
three gates and include the actual reviewed artifacts. The wrapper permits at most
48000 UTF-8 bytes and 100 artifacts. Larger evidence collections need a separately
implemented private storage integration; do not publish sensitive source files to
work around the limit. Repository secret access must be restricted to trusted code
and maintainers; anyone able to alter trusted Actions code may expose its secrets.

Use this local packaging pattern with your private register and evidence root:

```python
import base64
import json
from pathlib import Path
register = json.loads(Path('private-register.json').read_text())
root = Path('private/evidence').resolve()
artifacts = {}
for gate in register['gates'].values():
    for record in gate['evidence']:
        relative = Path(record['path'])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root):
            raise ValueError('Evidence must be inside the private root')
        artifacts[record['path']] = base64.b64encode(path.read_bytes()).decode()
Path('private-bundle.json').write_text(json.dumps({'register': register, 'artifacts': artifacts}))
```

Secure and remove temporary bundle copies according to your retention policy. Refresh
the secret when evidence or approvals change. The schedule never fabricates missing
artifacts, refreshes expiry dates or creates human approvals. Expired evidence and
reviews continue to fail until supplied by their owners.

The wrapper materializes evidence in a temporary private runner directory, validates
it, deletes it and writes only fixed statuses, gate eligibility and gap counts to
stdout and the job summary. It uploads no artifacts, uses no broker credentials and
sends no external notifications. Counts and pass/fail status remain visible in public
Actions runs. Missing configuration reports `NOT_CONFIGURED` and fails; malformed
bundles report `INVALID_EVIDENCE`; incomplete gates report `EVIDENCE_INCOMPLETE`.
A successful check is `ELIGIBLE_FOR_HUMAN_REVIEW`, never certification or execution
permission. Existing GitHub notification preferences determine failure notifications.
