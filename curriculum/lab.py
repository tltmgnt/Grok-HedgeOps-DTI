"""Offline curriculum answer key. Synthetic checks, never operational approval."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for base in (ROOT, ROOT / "src", ROOT / "layer-b"):
    sys.path.insert(0, str(base))
CASES = []

def check(name, actual, expected):
    passed = actual == expected
    CASES.append({"case": name, "actual": actual, "expected": expected, "passed": passed})
    if not passed:
        raise AssertionError(f"{name}: expected {expected!r}, got {actual!r}")

def rejects(name, call, error=ValueError):
    try:
        call()
    except error:
        check(name, error.__name__, error.__name__)
    else:
        raise AssertionError(f"{name}: expected {error.__name__}")




def run():
    # Import the original pure validator through its dependency-free module.
    from report_validation import ARRAY_FIELDS, REQUIRED_FIELDS, validate_report
    validate = validate_report
    r = {key: [] if key in ARRAY_FIELDS else "UNKNOWN" for key in REQUIRED_FIELDS}
    check("complete advisory schema", validate(json.dumps(r)), r)
    rejects("nonobject response", lambda: validate("[]"))
    rejects("missing report fields", lambda: validate("{}"))
    bad = copy.deepcopy(r); bad["evidence"] = "unsupported"
    rejects("evidence must be an array", lambda: validate(json.dumps(bad)))
    bad = copy.deepcopy(r); bad["recommendation"] = "An unverified assertion"
    check("schema accepts unverified prose: not factual validation", validate(json.dumps(bad))["recommendation"], "An unverified assertion")

if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--verify"]):
        raise SystemExit("Usage: python curriculum/lab.py [--verify]")
    run()
    report = {"schema_version": 1, "status": "PASS", "case_count": len(CASES),
              "cases": CASES, "scope": "Synthetic curriculum checks only"}
    if sys.argv[1:] == ["--verify"]:
        expected = json.loads((Path(__file__).parent / "expected.json").read_text())
        if report != expected:
            raise AssertionError("Observed answers differ from curriculum/expected.json")
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
