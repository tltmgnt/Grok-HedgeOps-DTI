# Dependency maintenance policy

Production dependencies are specified in `requirements.txt` using bounded
version ranges rather than unverified exact pins. CI installs resolved versions,
runs `pip check` and `pip-audit`, and Dependabot proposes weekly updates.

For a reproducible release, generate and review a Python-version-specific,
hash-locked requirements file with `pip-compile --generate-hashes` in a
controlled environment, then use `pip install --require-hashes` for deployment.
Do not manually invent transitive versions or hashes.

The offline paper simulator has no runtime third-party dependencies. The separate
autonomous paper experiment uses fixed Alpaca paper/data hosts and the standard
library. Real-money execution is not enabled. See docs/AUTONOMOUS_PAPER_SESSIONS.md.
