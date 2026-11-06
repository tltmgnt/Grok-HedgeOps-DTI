"""Validate offline demo outputs and write a fail-closed machine-readable report."""
import argparse
import json
import math
from pathlib import Path

def validate(result):
    if not isinstance(result, dict):
        raise ValueError("Simulation result must be an object")
    for name in ("starting", "ending", "return_pct", "observations", "trade_count"):
        value = result.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Missing or invalid {name}")
    if result["starting"] != 200 or result["ending"] < 0:
        raise ValueError("Unexpected capital or negative ending balance")
    if result["observations"] <= 0 or result["trade_count"] < 0:
        raise ValueError("Invalid observation or trade count")
    if not isinstance(result.get("trades"), list):
        raise ValueError("Missing trades list")
    if result["trade_count"] != len(result["trades"]):
        raise ValueError("Trade count mismatch")
    if len(result.get("equity_curve", [])) != result["observations"]:
        raise ValueError("Equity curve length mismatch")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in result["equity_curve"]):
        raise ValueError("Invalid equity curve")
    return {
        "status": "PASS",
        "mode": "OFFLINE_SYNTHETIC_ONLY",
        "broker_orders_submitted": 0,
        "starting_usd": result["starting"],
        "ending_usd": result["ending"],
        "observations": result["observations"],
        "trade_count": result["trade_count"],
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("simulation", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = validate(json.loads(args.simulation.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        report = {"status": "FAIL", "mode": "OFFLINE_SYNTHETIC_ONLY",
                  "broker_orders_submitted": 0, "reason": str(exc)}
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
