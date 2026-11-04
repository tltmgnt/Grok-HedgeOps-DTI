import pytest
from paper_trader import prices_demo, simulate


@pytest.mark.parametrize("capital", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_capital_rejected(capital):
    with pytest.raises(ValueError):
        simulate(prices_demo(), capital=capital)
