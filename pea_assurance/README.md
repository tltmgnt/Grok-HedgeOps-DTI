# Psychometric Epistemic Assurance (PEA)

Experimental measurement layer for Psychometrician × ResearchOS × TECT.
This is the repository owner's proposed research extension, not an independently
validated capability, truth detector, or production assurance authority.

## Architecture

ResearchOS supplies versioned claims, evidence, provenance and reproducibility
records. A psychometric measurement layer evaluates the quality and limitations
of assurance measurements. The TECT controller retains responsibility for
validation, adversarial challenge, governance and authorized state transitions.
The intended output is an accepted, rejected or uncertain **promotion decision
within an explicit evidence scope**, with unresolved obligations retained.

This module is an offline sidecar with no dependencies beyond Python 3.9+.
It does not modify existing controllers, evidence registers, permissions or
domain adapters. Its advisory result must not directly promote a live claim.

## Run and verify

From the repository root:

```sh
python -m unittest pea_assurance.test_measurement -v
python -m pea_assurance pea_assurance/synthetic_example.json
```

The fixture is synthetic and returns Brier score 0.04 and ECE 0.2, within
floating-point precision. These numbers test arithmetic; they are not pilot
findings. The CLI exits 2 for invalid measurement data.

## Release consistency

Release 0.1.1 adds a dependency-free local consistency checker:

```sh
python -m pea_assurance.verify_release --repository OWNER/REPOSITORY
python -m unittest pea_assurance.test_measurement pea_assurance.test_release -v
```

Replace OWNER/REPOSITORY with this checkout's exact GitHub owner and repository.
The dedicated PEA workflow runs the checker, all 20 synthetic tests and the
measurement CLI on pull requests and pushes to main. It has read-only repository
permissions, installs no project dependencies and makes no model/provider calls.
It is not scheduled monitoring or a scientific assurance evaluation.

The checker requires the complete file inventory, SHA-256 digests, matching
repository/version/domain metadata, the white-paper digest, and explicit
unvalidated/advisory scope. Tampering, omitted files, paths escaping the checkout
and unsupported scope claims fail with exit 2. A consistent local manifest is
not an authenticated release signature: changing both files and their hashes can
still produce internally consistent records. Independent validation remains open.

## Implemented measurement contract

`calibration(probabilities, outcomes, bins=10)` consumes aligned binary claim
probabilities and externally adjudicated integer labels (0 or 1). Probability
means the predicted probability of label 1, not confidence in the selected
answer. Outputs: sample count, binary Brier score, equal-width ECE and per-bin
counts/means. Bins are left-closed/right-open except the final bin includes 1.
Empty samples and empty-bin estimates return null, never perfect calibration.
Unresolved labels are rejected: exclude and count them explicitly in the study
report. ECE depends on binning and sample composition; low ECE alone cannot
establish validity. The implementation provides no uncertainty intervals or
calibration fitting, and makes no inference about correlated observations.

`agreement(first, second)` consumes two aligned lists of categorical ratings.
Outputs: observed agreement and Cohen kappa. Empty samples and degenerate
marginals return null for undefined estimates. Call on matched item IDs, not
arbitrarily ordered ratings. Consistent agreement can still be consistently wrong.
Multi-rater, crossed-effects and test-retest analyses remain study work.

`scoped_decision(claim_id=..., scope=..., policy_version=...,
evidence_refs=[...], checks={...})` aggregates external assessments of six
required obligations: validity, calibration, provenance, reproduction,
adversarial and governance. Each status is PASS, FAIL, UNCERTAIN, ERROR or
SKIPPED; omitted obligations become UNCERTAIN. Any FAIL rejects promotion;
otherwise a missing reference or unresolved obligation yields uncertainty.
Only all PASS with evidence references produces advisory acceptance. A FAIL
means the promotion policy was not satisfied; it does not prove factual falsity.
There are deliberately no default numerical acceptance thresholds.

The output retains claim ID, scope, policy version, evidence references and
normalized checks. `advisory_only=true` and `empirically_validated=false` remain
explicit. Caller-supplied PASS statuses and references are not authenticated or
verified by this helper. Authoritative use would require resolved evidence
artifacts, authorized reviewer identities, version/hash binding, policy
thresholds selected on development data, held-out calibration, expiry checks,
and a controller adapter that re-evaluates changed dependencies.

## Research record requirements

For each observation retain task/claim/version IDs; domain; blinded condition;
model/version or evaluator pseudonym; trial ID; task difficulty annotation;
probability; adjudicated label or unresolved reason; rubric version; source
cluster IDs; evidence artifact hashes and access scope; policy version;
validation/challenge outcomes; elapsed time and reviewer effort. Keep sensitive
evidence outside public repositories and CI. Separate calibration-fit,
validation-selection and held-out evaluation partitions by task and source
cluster, not individual repeated ratings. Record unavailable data and exclusions.

## Research roadmap and boundaries

See [technical proposal](../docs/researchos/PEA_RESEARCH.md) and
[pilot protocol](pilot_protocol.json). Construct validity, IRT, factor analysis,
differential item functioning, fitted calibration, uncertainty estimation and
empirical superiority are proposed work. No fitted latent models, human study,
clinical authorization or institutional engagement is claimed. PEA describes a
potential independent research and consulting specialization; it does not imply
employment, endorsement, partnership or validation by JPMorgan Chase or any
other institution.
