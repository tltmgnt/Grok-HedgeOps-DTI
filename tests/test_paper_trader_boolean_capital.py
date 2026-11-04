import pytest

from paper_trader import prices_demo, simulate


@pytest.mark.parametrize("capital", [True, False])
def test_boolean_capital_rejected(capital):
    with pytest.raises(ValueError):
        simulate(prices_demo(), capital=capital)
