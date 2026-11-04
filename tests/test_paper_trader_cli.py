import sys
from unittest.mock import patch

import pytest

from paper_trader import main


def test_demo_cli(capsys):
    with patch.object(
        sys, "argv",
        ["paper_trader.py", "--demo", "--capital", "200"]
    ):
        main()

    output = capsys.readouterr().out
    assert "PAPER ONLY" in output
    assert "starting: 200.0" in output
    assert "ending:" in output
    assert "return_pct:" in output
    assert "max_drawdown_pct:" in output
    assert "trades:" in output


def test_csv_cli(tmp_path, capsys):
    path = tmp_path / "prices.csv"
    path.write_text(
        "date,close\n"
        + "".join(f"{i},{100 + i}\n" for i in range(1, 31)),
        encoding="utf-8",
    )

    with patch.object(
        sys, "argv",
        ["paper_trader.py", "--csv", str(path)]
    ):
        main()

    output = capsys.readouterr().out
    assert "PAPER ONLY" in output
    assert "starting: 200.0" in output


def test_cli_requires_data_source():
    with patch.object(sys, "argv", ["paper_trader.py"]):
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 2
