"""Inspect a local release evidence JSON file; never deploy or merge."""
import argparse
import json
from pathlib import Path
from hedgeops.release_gate import assess_release, REQUIRED

def main():
    parser = argparse.ArgumentParser(description="Read-only release readiness gate")
    parser.add_argument("evidence", type=Path, help="JSON evidence file")
    args = parser.parse_args()
    data = json.loads(args.evidence.read_text(encoding="utf-8"))
    result = assess_release(data)
    print(json.dumps({"eligible_for_human_release_review": result.eligible,
                      "missing": result.missing}, indent=2))
    if not result.eligible:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
