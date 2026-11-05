"""Safety tests for the manual paper-only Purchase Now action."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from purchase_now import prepare_purchase

ROOT = Path(__file__).resolve().parents[1]


def test_purchase_request_never_executes():
    item = prepare_purchase("SPY", 50)
    assert item["status"] == "pending_human_review"
    assert item["execution_mode"] == "paper_only"
    assert item["side"] == "BUY"
    assert item["requested_notional"] == 50.0
    assert item["order_submitted"] is False
    assert item["order_executed"] is False
    assert item["broker_order_id"] is None
    assert item["requires_human_review"] is True


@pytest.mark.parametrize("symbol", ["", "spy", "SPY;echo hacked", "../SPY", "X" * 16])
def test_invalid_symbols_rejected(symbol):
    with pytest.raises(ValueError):
        prepare_purchase(symbol, 50)


@pytest.mark.parametrize("amount", [0, -1, 200.01, float("nan"), float("inf"), True])
def test_invalid_notional_rejected(amount):
    with pytest.raises(ValueError):
        prepare_purchase("SPY", amount)


def test_live_mode_rejected():
    with pytest.raises(ValueError):
        prepare_purchase("SPY", 10, paper_only=False)


def test_cli_writes_only_pending_request(tmp_path):
    output = tmp_path / "request.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "purchase_now.py"), "--symbol", "SPY",
         "--notional", "25", "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "NO ORDER SUBMITTED" in result.stdout
    payload = json.loads(output.read_text())
    assert payload["order_submitted"] is False
    assert payload["status"] == "pending_human_review"


def test_cli_invalid_value_fails_closed(tmp_path):
    output = tmp_path / "request.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "purchase_now.py"), "--symbol", "SPY",
         "--notional", "500", "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert not output.exists()
