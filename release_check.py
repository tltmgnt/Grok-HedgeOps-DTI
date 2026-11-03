"""Offline release candidate checks. No API calls, no production writes."""
import argparse
import compileall
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run offline release validation")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not compileall.compile_dir(str(ROOT / "hedgeops"), quiet=1):
        raise SystemExit("FAIL: Python source compilation")
    targets = [name for name in ("agent.py", "lab.py", "live_case.py",
               "integrated_demo.py", "operator_cli.py", "persistent_demo.py",
               "feedback_demo.py") if (ROOT / name).exists()]
    for name in targets:
        if not compileall.compile_file(str(ROOT / name), quiet=1):
            raise SystemExit(f"FAIL: compilation of {name}")
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests"]
    if args.verbose:
        command.append("-v")
    print("Running:", " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("PASS: offline compilation and unit tests")
    print("NOT VERIFIED: live xAI API, authenticated approval, production deployment")

if __name__ == "__main__":
    main()
