"""Operator-only case review and recovery. Tokens are read from environment."""
import argparse
import json
import os
from hedgeops.store import EventStore
from hedgeops.operations import authorized_review, recover_analysis
from hedgeops.live import create_grok_ask

def main():
    parser = argparse.ArgumentParser(description="Review or recover a case")
    parser.add_argument("--db", default=os.getenv("HEDGEOPS_DB_PATH", "data/hedgeops.sqlite3"))
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review")
    review.add_argument("case_id")
    review.add_argument("decision", choices=["approved_for_tracking", "rejected", "needs_revision"])
    review.add_argument("--reviewer", required=True)
    review.add_argument("--rationale", required=True)
    recovery = sub.add_parser("recover")
    recovery.add_argument("case_id")
    args = parser.parse_args()
    with EventStore(args.db) as store:
        if args.command == "review":
            result = authorized_review(
                store, args.case_id, args.decision, args.reviewer, args.rationale,
                os.getenv("HEDGEOPS_OPERATOR_TOKEN"))
        else:
            # Recovery requires the same operator secret, but never prints it.
            from hedgeops.operations import require_operator_token
            require_operator_token(os.getenv("HEDGEOPS_OPERATOR_TOKEN"))
            result = recover_analysis(store, args.case_id, create_grok_ask())
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, PermissionError, KeyError) as exc:
        raise SystemExit(f"Error: {exc}") from exc
