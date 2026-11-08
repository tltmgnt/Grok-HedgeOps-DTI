"""Always-running paper session worker. Stops on errors; never blindly retries."""
import argparse
import json
from workflow_ledger import Ledger
from datetime import datetime, timezone
from pathlib import Path
import time
from paper_research_agent import main as session_main


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('data/paper-research'))
    parser.add_argument('--interval-seconds', type=int, default=60)
    parser.add_argument('--monitor-only', action='store_true')
    parser.add_argument('--ledger', type=Path, default=Path('data/workflow-ledger.sqlite3'))
    args = parser.parse_args(argv)
    if args.interval_seconds < 60:
        parser.error('minimum polling interval is 60 seconds')
    try:
        while True:
            run = args.output_dir / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            command = ['--output-dir', str(run)]
            if args.monitor_only:
                command.append('--monitor-only')
            code = session_main(command)
            ledger = Ledger(args.ledger)
            try:
                ledger.ingest(str(run.resolve()), json.loads((run / 'session.json').read_text()))
            finally:
                ledger.close()
            if code:
                return code  # Reconcile the broker before manually restarting.
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
