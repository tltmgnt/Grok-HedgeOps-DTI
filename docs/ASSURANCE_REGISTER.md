# Evidence register and automated completeness checks

This read-only tool implements three separate evidence-completeness gates:
`trading_evidence`, `investor_fit` and `operational_assurance`. Every gate requires
an owner, scope, subject ID, criteria version and evidence for every required category. The checker evaluates completeness automatically. It never submits orders,
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

The local report includes a packet SHA256 for each gate covering its fields and
strategy version. Legacy `review` metadata is ignored when hashing and assessing
a gate. Each gate reports `evidence_complete`. Exit code 0 means all three pass,
1 means evidence is incomplete and 2 means the register or input is malformed.
Execution authorization and certification are always false.

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

Tests cover unsigned and legacy registers, independent gate results, artifact
integrity, timestamps, path confinement, subject and strategy binding, blockers
and duplicate requirements.

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
three gates and include the actual evidence artifacts. The wrapper permits at most
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
the secret when evidence changes. The schedule never fabricates missing
artifacts, refreshes expiry dates or creates human approvals. Expired evidence fails until refreshed.

The wrapper materializes evidence in a temporary private runner directory, validates
it, deletes it and writes only fixed statuses, gate eligibility and gap counts to
stdout and the job summary. It uploads no artifacts, uses no broker credentials and
sends no external notifications. Counts and pass/fail status remain visible in public
Actions runs. When invoked directly without a bundle or import file, `scheduled_assurance.py`
returns `SKIPPED_NOT_CONFIGURED`. The **GitHub Actions workflow** differs: if the
private secret is empty, it first attempts to import fresh verified results from
`hourly-offline-release.yml`. This offline synthetic evidence intentionally
satisfies **none** of the 20 independently reviewed requirements, so successful
import yields `EVIDENCE_INCOMPLETE` and a failed job. If no suitable recent
artifact exists, the import itself fails closed. The synthetic importer cannot
complete private assurance. Both triggers fail on malformed bundles
(`INVALID_EVIDENCE`) or incomplete gates (`EVIDENCE_INCOMPLETE`).
A completed evidence assessment reports `EVIDENCE_COMPLETE`, never certification or execution
permission. Existing GitHub notification preferences determine failure notifications.

### Activation incident: November 8, 2026

Run 42478302602 completed checkout and Python setup, then failed with
`NOT_CONFIGURED`: the evidence-bundle environment value was empty. PR #53
introduced the schedule but explicitly left the private secret unconfigured.
The hourly offline simulation covers a different scope and cannot close this gate.

To activate assessment, package the private register and its evidence artifacts,
configure the named repository Actions secret, and verify `EVIDENCE_COMPLETE` in
a subsequent run. A skipped local assessment is not a passing private-evidence gate.

### Follow-up incident: November 13, 2026

The scheduled workflow imported a verified successful hourly offline run but
reported `EVIDENCE_INCOMPLETE`: 6 missing investor-fit categories, 7 missing
operational-assurance categories, and 7 missing trading-evidence categories,
plus missing scope metadata in each gate. This is expected for the intentionally
unattested synthetic import, not a scheduler or Python installation failure.

**Remediation:** Have the authorized reviewers independently produce and attest
the complete private register and actual evidence artifacts described above;
package them locally, verify their SHA256 hashes and expiry, then set
`ASSURANCE_EVIDENCE_BUNDLE_JSON` as a restricted repository Actions secret.
Never publish private investor/account data or fabricate evidence to make the
workflow green. Re-run **Scheduled Evidence Gates** manually after configuration
and verify the redacted gate status, not just the job color.
