"""Evaluate GitHub's UTC cron against 9 AM America/Los_Angeles, including DST.

Use scheduled UTC *slot*, not actual runner start time (which may be delayed).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CRONS = {"0 16 * * *": 16, "0 17 * * *": 17}

def decide(event_name, cron, run_date):
    if event_name == "workflow_dispatch":
        return True, "MANUAL_SIMULATION_REQUEST"
    if event_name != "schedule":
        return False, "UNSUPPORTED_EVENT"
    if cron not in CRONS:
        return False, "UNRECOGNIZED_CRON"
    if run_date.tzinfo is None:
        raise ValueError("run_date must be timezone aware")
    utc_date = run_date.astimezone(timezone.utc).date()
    nominal = datetime(utc_date.year, utc_date.month, utc_date.day,
                       CRONS[cron], tzinfo=timezone.utc)
    pacific = nominal.astimezone(ZoneInfo("America/Los_Angeles"))
    if pacific.hour == 9:
        return True, "PACIFIC_9AM_SCHEDULE"
    return False, "DST_ALTERNATE_CRON"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--cron", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    allowed, reason = decide(args.event, args.cron, datetime.now(timezone.utc))
    args.output.write_text("run=" + str(allowed).lower() + "\nreason=" + reason + "\n")
    with args.summary.open("a", encoding="utf-8") as f:
        f.write("## Offline paper simulation schedule\n\n")
        f.write(f"- Decision: **{'RUN' if allowed else 'SKIP'}**\n")
        f.write(f"- Reason: `{reason}`\n")
        f.write(f"- Event: `{args.event}`\n")
        f.write(f"- Scheduled cron: `{args.cron or 'manual'}`\n")
        f.write("- Execution mode: offline synthetic simulation only; no broker calls\n")
    print(json.dumps({"run": allowed, "reason": reason}))

if __name__ == "__main__":
    main()
