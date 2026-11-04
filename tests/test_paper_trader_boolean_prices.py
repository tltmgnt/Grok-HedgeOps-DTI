import pytest

from paper_trader import prices_demo, simulate


@pytest.mark.parametrize("price", [True, False])
def test_boolean_price_rejected(price):
    data = list(prices_demo())
    date, _ = data[-1]
    data[-1] = (date, price)

    with pytest.raises(ValueError):
        simulate(data, capital=200)
