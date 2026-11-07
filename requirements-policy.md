# Dependency maintenance policy

## Manifests and reviewed locks

- `requirements.in` declares bounded production dependencies.
- `requirements.txt` locks production and transitive dependencies to exact versions
  and SHA-256 artifact hashes.
- `requirements-dev.in` declares test/security tools and includes production inputs.
- `requirements-dev.txt` locks the complete development/CI environment, constrained
  to the production lock so shared packages cannot drift between environments.

The locks are generated with **uv 0.13.5**, universal resolution, and a Python 3.10
minimum. Conditional markers retain compatible versions for different Python
versions/platforms. CI validates Linux on Python 3.10, 3.12 and 3.13; other platforms
are not certified merely because universal markers are present.

Install into a clean virtual environment:

```sh
python -m venv .venv
# Production:
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements.txt
# Development and CI (includes production dependencies):
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python scripts/check_dependency_policy.py
```

The policy checker runs in the development/CI environment, where its parsing tools
are locked. For a production-only installation, run `python -m pip check`.
Hash verification authenticates downloaded bytes against the reviewed lock; it
is not proof that an upstream package is benign. Wheel-only installation avoids
unlocked source-build dependencies. If a platform has no matching wheel, stop
and review that platform rather than disabling verification.

## Updating dependencies

Install the fixed compiler in a separate development environment:

```sh
python -m pip install 'uv==0.13.5'
# Reconcile manifest edits while retaining still-compatible locked versions:
python scripts/lock_dependencies.py
# Deliberately refresh allowed package versions:
python scripts/lock_dependencies.py --upgrade
# Check regeneration without changing the committed files:
python scripts/lock_dependencies.py --check
```

Review both generated lockfiles, source release notes and dependency changes.
Commit the `.in` edits and regenerated `.txt` files together. Never invent hashes
or manually replace an artifact hash to make an installation pass.

CI installs the locked development environment with hash verification, checks
installed versions against both locks and input constraints, runs the full suite
on the three supported Python versions, and runs `pip-audit` plus Bandit. A failed
audit, incompatible lock, missing hash, or failed test must be resolved before
merging. The scanner databases remain live external inputs; their results are not
frozen by the tool-version lock.

## GitHub Actions and Dependabot

All workflow actions use full 40-character commit SHAs with readable version
comments. The action SHAs were resolved from the official repositories' v7 refs;
checkout, setup-python and upload-artifact each use one consistent commit across
workflows. CI rejects mutable references and inconsistent commits for the same
action. Dependabot can update pinned action references; review the new upstream
commit, release notes and CI before merging.

Dependabot retains weekly `pip` and `github-actions` updates. Python updates are
grouped so shared lockfile changes can be reviewed together. Auto-merge remains
disabled. Dependabot may propose changes that need lock regeneration; CI rejects
inconsistent installed versions rather than silently accepting them.

Broker/xAI credentials are used only by the existing explicitly scoped operational
steps, not dependency-test or security-audit jobs. Do not copy trading credentials
into Dependabot secrets to make dependency PRs pass.

Dependabot security-alert/security-update settings are repository settings separate
from this file and remain unverified through the available connector. GitHub also
notes limitations to security alerts for SHA-pinned action references; keep weekly
version updates and upstream advisory review. These changes do not assert that
all vulnerabilities can be detected.

## Scope

This locks Python package artifacts and workflow action commits, not the entire
operating system, Python distribution, hosted-runner image or external APIs.
Trading rules, paper-only destinations and order permissions are unchanged.
