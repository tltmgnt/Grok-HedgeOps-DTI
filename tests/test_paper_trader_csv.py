import pytest
from paper_trader import prices_csv


def test_csv_loads_valid_prices(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text(
        "date,close\n2026-01-01,100\n2026-01-02,105\n",
        encoding="utf-8",
    )

    assert list(prices_csv(path)) == [
        ("2026-01-01", 100.0),
        ("2026-01-02", 105.0),
    ]


def test_csv_rejects_missing_close_column(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("date,open\n2026-01-01,100\n")

    with pytest.raises(ValueError, match="close column"):
        list(prices_csv(path))


@pytest.mark.parametrize("invalid_price", ["0", "-5", "nan", "inf"])
def test_csv_rejects_invalid_prices(tmp_path, invalid_price):
    path = tmp_path / "prices.csv"
    path.write_text(f"date,close\n2026-01-01,{invalid_price}\n")

    with pytest.raises(ValueError, match="finite and positive"):
        list(prices_csv(path))


def test_csv_uses_row_number_without_date(tmp_path):
    path = tmp_path / "prices.csv"
    path.write_text("close\n100\n105\n")

    assert list(prices_csv(path)) == [
        ("1", 100.0),
        ("2", 105.0),
    ]
