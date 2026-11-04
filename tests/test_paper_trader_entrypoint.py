import subprocess
import sys
from pathlib import Path


def test_script_entrypoint():
    script = Path(__file__).resolve().parents[1] / "paper_trader.py"

    result = subprocess.run(
        [sys.executable, str(script), "--demo", "--capital", "200"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert "PAPER ONLY" in result.stdout
    assert "starting: 200.0" in result.stdout
    assert "ending:" in result.stdout
    assert "return_pct:" in result.stdout
    assert "max_drawdown_pct:" in result.stdout
