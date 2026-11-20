# MathOS × — bounded autonomous proof search, novelty audit and code PR agent

**Implemented scope (2026-11-18):** autonomous enumeration of consequences of human-registered finite XOR theories, independent exact proof replay, finite-corpus originality triage, and scheduled deterministic code changes **proposed via GitHub pull requests**. **Not** a general theorem prover, not a universal mathematical novelty detector, and not an agent that autonomously merges or rewrites arbitrary code.

## Exact theorem-proving capability

`mathosx/autonomy.py` validates systems of at most 32 parity equations over at most 10 binary variables. It uses GF(2) Gaussian elimination to construct a certificate: a list of input-equation indices whose XOR yields the contradiction `0=1`. To establish `A => C`, the prover refutes `A ∧ ¬C`; an independent checker replays the certificate and brute-force checks all assignments. For non-entailment, the prover returns a concrete satisfying countermodel. Inconsistent axioms are reported separately rather than masquerading as discoveries.

Finite candidate generation automatically enumerates parity conclusions (up to three variables per conclusion) from the registered systems. Every output retains its source axioms and replayable certificate. Passing a finite formal check **proves only that exact finite XOR statement**, not any broad theorem or a new mathematical field.

## Novelty: what can and cannot be proved

`mathosx/known_claims.v1.json` is an explicitly limited, versioned local corpus. We can **prove syntactic nonidentity relative to that finite corpus** by comparing normalized statement hashes, with the corpus digest included in every report. This is **not** a proof of mathematical novelty: equivalently worded claims, alpha-renaming, external literature, preprints, unpublished results, and different but equivalent formulations are not checked. All results retain `global_mathematical_novelty=NOT_ESTABLISHED`, `literature_review=NOT_PERFORMED`, and `global_theorem_certification=NOT_CERTIFIED`. A claim of external originality requires researcher-led literature search and independent mathematical review.

## Reproduce locally

Requires Python 3.10+ and only the Python standard library.

```sh
python -m unittest discover -s tests -p 'test_mathosx_autonomy.py' -v
python -m mathosx.autonomy --output-dir artifacts/mathosx-autonomous
python -m mathosx.autonomy --generate-code
python -m mathosx.autonomy --check-code
python -c 'from mathosx.generated_theorems import recheck; assert recheck()'
```

The `--generate-code` command writes **only** `mathosx/generated_theorems.py`; its fixed template embeds escaped JSON records backed by rechecked certificates. No arbitrary AI-authored source is evaluated. Change reviewed problem inputs to obtain different finite consequences. Codegen is **not** production execution of mathematical results.

## Automatic code-updating agent

`.github/workflows/mathosx-code-proposals.yml` is scheduled weekly and manually dispatchable **on the protected default branch only**. It runs proof tests, generates the allowlisted code module, independently rechecks its certificates, and, **only if the module changed**, pushes a dedicated branch and opens a PR. No unattended merge, remote model/API expenditure, application runtime update, or edit to proof-certification registers occurs.

The scheduled workflow has `contents:write` and `pull-requests:write` permission exclusively for creating a Git branch and PR, and must be permitted by the repository's GitHub Actions settings. If GitHub blocks PR creation by `GITHUB_TOKEN`, the job fails visibly and does not bypass the restriction. A human must review every generated source change before it enters `main`.

The separate `mathosx-prover-ci.yml` tests have read-only permissions and run on pull requests. Workflow changes should be treated as security-sensitive and reviewed carefully. Independent assessment is required before applying any mathematical output to operational, financial, medical, defense, or scientific decisions.

**Status:** automated finite theorem exploration is real and testable; globally verified mathematical originality and unrestricted autonomous theorem proving are *not* implemented and cannot be responsibly claimed.
