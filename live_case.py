"""Run live five-agent Grok analysis and persist it under a new case ID."""
import argparse
import json
import logging
import os
from hedgeops.live import create_grok_ask, GrokServiceError
from hedgeops.store import EventStore
from hedgeops.workflow import create_case, replay

def main(argv=None):
    parser = argparse.ArgumentParser(description="Persistent live Grok HEDGE 302 case")
    parser.add_argument("problem", help="Problem for the five-agent laboratory")
    parser.add_argument("--db", default=os.getenv("HEDGEOPS_DB_PATH", "data/hedgeops.sqlite3"))
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 180:
        parser.error("--timeout must be between 0 and 180 seconds")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ask = create_grok_ask(timeout=args.timeout)
    with EventStore(args.db) as store:
        case_id = create_case(store, args.problem, ask)
        print(json.dumps(replay(store, case_id), indent=2))
        print("Global event chain valid:", store.verify_chain())

if __name__ == "__main__":
    try:
        main()
    except (ValueError, GrokServiceError) as exc:
        raise SystemExit(f"Error: {exc}") from exc
