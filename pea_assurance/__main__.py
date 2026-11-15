"""Run: python -m pea_assurance path/to/adjudicated.json"""
import argparse
import json
from .measurement import calibration


def main():
    parser = argparse.ArgumentParser(description="Experimental PEA binary calibration diagnostics")
    parser.add_argument("input", help="JSON object with probabilities, outcomes, optional bins")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as source:
            data = json.load(source)
        result = calibration(data["probabilities"], data["outcomes"], data.get("bins", 10))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"Invalid measurement input: {error}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
