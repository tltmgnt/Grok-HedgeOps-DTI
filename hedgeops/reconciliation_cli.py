"""Read-only JSON operator CLI for reconciliation readiness."""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from hedgeops.https_custody import HTTPSExecutionCheckpointCustodian
from hedgeops.reconciliation_diagnostics import readiness_diagnostics

EXIT_READY = 0
EXIT_DENIED = 2
EXIT_ERROR = 3

# Stable monitoring contract: evidence denials are not operational failures.
_DENIAL_CODES = frozenset({
    "PENDING_RECONCILIATION", "LOCAL_INTEGRITY_FAILURE",
    "CHECKPOINT_MISMATCH", "CUSTODY_UNVERIFIED", "LOCAL_STATE_CHANGED",
})
_ERROR_CODES = frozenset({
    "LOCAL_STATUS_UNAVAILABLE", "READINESS_UNAVAILABLE",
})


def readiness_exit_code(report):
    """Classify only known, internally consistent diagnostic results."""
    if not isinstance(report, dict):
        return EXIT_ERROR
    reason = report.get("reason_code")
    ready = report.get("ready")
    if type(ready) is not bool:
        return EXIT_ERROR
    if ready and reason == "READY" and report.get("custody_verified") is True:
        return EXIT_READY
    if not ready and reason in _DENIAL_CODES:
        return EXIT_DENIED
    if not ready and reason in _ERROR_CODES:
        return EXIT_ERROR
    return EXIT_ERROR


class ReadOnlyAuthority:
    def __init__(self, path):
        self.path = str(Path(path).resolve())

    def _connect(self):
        return sqlite3.connect(
            "file:" + self.path.replace("?", "%3F").replace("#", "%23") +
            "?mode=ro", uri=True, timeout=10)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only custody readiness JSON")
    parser.add_argument("--database", required=True)
    parser.add_argument("--checkpoint", required=True,
                        help="Path to authenticated checkpoint JSON")
    parser.add_argument("--custody-url", required=True,
                        help="HTTPS /v1/execution-checkpoint endpoint")
    args = parser.parse_args(argv)
    try:
        with open(args.checkpoint, encoding="utf-8") as source:
            checkpoint = json.load(source)
        key = bytes.fromhex(os.environ["HEDGEOPS_EXECUTION_CHECKPOINT_KEY_HEX"])
        token = os.environ["HEDGEOPS_CUSTODY_BEARER_TOKEN"]
        custodian = HTTPSExecutionCheckpointCustodian(args.custody_url, token)
        report = readiness_diagnostics(
            ReadOnlyAuthority(args.database), checkpoint, key, custodian)
        code = readiness_exit_code(report)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        report = {"ready": False, "reason_code": "READINESS_UNAVAILABLE",
                  "message": "Readiness check could not be completed.",
                  "pending": None, "confirmed": None, "audit_head": None,
                  "custody_verified": False}
        code = EXIT_ERROR
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    sys.exit(main())
