import pytest

from paper_trader import prices_demo, simulate


@pytest.mark.parametrize("fee", [True, False])
def test_boolean_fee_rejected(fee):
    with pytest.raises(ValueError):
        simulate(prices_demo(), fee=fee)
