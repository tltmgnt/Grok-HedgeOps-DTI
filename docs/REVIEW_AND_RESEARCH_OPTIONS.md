# Repository options for review and research

These are documentation and development paths, not executable modes, certifications, or completed approvals. Choose a path by the claim you intend to make. Independent review and testing must precede formal academic submission.

| Option | Objective | Appropriate claim after evidence is collected | Required deliverables |
|---|---|---|---|
| A — Prototype review (recommended starting point) | Establish what the implementation does and where it fails | The specified implementation passes the documented checks on the reviewed release | Pinned release, claim inventory, reproducible setup, test logs, independent code review, resolved or disclosed findings |
| B — Comparative research | Test whether DTI / HedgeOps adds value over simpler approaches | A precisely scoped improvement on the declared dataset and metrics, if supported by results | Option A evidence, preregistered protocol, provenance, baselines, ablations, uncertainty estimates, independent reproduction |
| C — Operational validation | Establish whether a particular deployment's controls work | Specific controls passed specified integration and failure tests in the named environment | Option A evidence, identity and authorization review, paper integration, reconciliation, concurrency and recovery tests, environment configuration review |

Option B does not require live trading. Option C does not establish investment performance or academic novelty. A negative or null result is a valid research outcome.

## Review baseline

A focused local review of commit `442eac5170da7a8b26f2173232d6b50c799455fc` recorded:
- Python 3.12: 332 tests and 37 subtests passed using `python -m pytest tests/ -q`.
- `python release_check.py` passed compilation and the offline suite.
- `python -m pip check` reported no broken requirements.
- Live xAI behavior, broker execution, configured approval controls, and other Python versions were not verified.

These results describe that commit and local environment only. They are not evidence that later commits pass or that external independent review has occurred.

## Option A — Prototype review

1. Freeze the exact commit and record Python and dependency versions. Archive sanitized logs and test inputs.
2. Inventory each public claim with its implementation path, test, evidence, limitation, and status.
3. Reproduce tests in a clean environment using the commands below.
4. Have a reviewer who did not implement the component inspect input validation, decision logic, evidence handling, and failure behavior.
5. Resolve findings or explicitly document their effect on the proposed claims.
6. Update README and older phase documents to match the reviewed release.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt 'pytest>=8,<10'
python -m pip freeze
python -m pip check
python -m pytest tests/ -q
python release_check.py
```

The offline suite uses mocks and synthetic inputs; passing it does not establish provider or broker integration reliability.

## Option B — Comparative research

Before collecting evaluation results, specify:
- The hypothesis, primary metric, minimum meaningful effect, evaluation population, and failure criteria.
- Versioned data sources, collection dates, licensing, preprocessing, missing-data policy, and chronological splits.
- A simple baseline, current framework, and ablations removing temporal reasoning, strategic input, or arbitration.
- Identical forecast origins and horizons, coverage and abstention reporting, and an uncertainty method appropriate to dependence and sample size.
- Model IDs, prompts, settings, repeated-run policy, and cost where an LLM is involved.

Keep generic decision-quality experiments separate from market-direction experiments. Use independent, blinded scoring where human judgment is required. Publish null results and limitations, then require an external researcher to reproduce the main tables.

Do not interpret the existing `mean_realized_return` as strategy P&L: it averages underlying price returns regardless of action. Profitability evaluation would additionally need explicit position accounting, execution timing, costs, slippage, and bias controls.

## Option C — Operational validation

Begin with isolated paper credentials and controlled integration scenarios. Record evidence for:
- Paper/live separation and approval enforcement at every relevant entry point.
- Stable request identifiers, ambiguous submission handling, reconciliation, and duplicate prevention.
- Stale data, API failures, alert delivery failures, partial execution, concurrent workers, and recovery.
- Secret handling, data retention, identity, authorization, and deployment configuration.

Inspect the actual configured GitHub environments; repository YAML alone does not prove required reviewers or restrictions are active. No change to broker settings, scheduled execution, credentials, or live trading is authorized by selecting this documentation path.

## Initial claims and evidence register

| Claim or finding | Current evidence | Required action before stronger claims |
|---|---|---|
| Agent rejects some malformed reports | Required fields and array containers are checked in `agent.py` | Validate scalar fields, array items, and evidence structure; add adversarial cases |
| Multi-agent agreement is independent | Default strategic action mirrors the temporal action in `hedgeops_team/core.py` | Treat default behavior as a deterministic baseline; document adapter provenance and shared failure modes |
| Confidence is calibrated | Non-HOLD team confidence is fixed at 0.6 | Label it a heuristic score until out-of-sample calibration evidence exists |
| Evaluation measures trading profit | Existing summary averages underlying returns | Use accurate metric naming and a separate accounting model before making profit claims |
| Offline test suite passes | Local results at the pinned review commit above | Re-run on the release candidate and archive full environment and logs |
| System improves decision quality | Not established by unit tests | Execute Option B against predefined baselines |
| Production controls are effective | Not verified by the focused local review | Execute Option C in the actual deployment |

## Submission gate

Before formal submission, require:
- [ ] Every paper claim maps to versioned evidence and a stated limitation.
- [ ] The implementation and documentation agree.
- [ ] Review findings are resolved or their effects are disclosed.
- [ ] Independent reviewers have examined the relevant code and methods.
- [ ] An independent reproduction of the main findings is recorded.
- [ ] Results, uncertainty, baselines, and negative outcomes are reported.
- [ ] The reviewed release, dependencies, data or access instructions, and reproducibility commands are archived.
- [ ] Attribution, conflicts, data provenance, and applicable ethics disclosures are included.

Suggested current wording: **Experimental prototype available for independent technical review and empirical evaluation.**
