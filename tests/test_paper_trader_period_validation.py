import pytest

from paper_trader import prices_demo, simulate


@pytest.mark.parametrize(
    "fast, slow",
    [(5.5, 20), (5, 20.5), (5.0, 20)],
)
def test_noninteger_periods_rejected(fast, slow):
    with pytest.raises(ValueError):
        simulate(prices_demo(), fast=fast, slow=slow)
