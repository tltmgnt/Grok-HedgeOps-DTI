"""Account risk boundaries, including changes between assessment and submission."""
from datetime import datetime, timezone
import os
from unittest.mock import patch

import pytest
import paper_opportunity_intelligence as trader

NOW = datetime.now(timezone.utc)
FLAGS = {'PAPER_AUTO_TRADING_ENABLED': 'true', 'PAPER_AUTO_KILL_SWITCH': 'false',
         'PAPER_ALLOCATION_MODE': 'legacy'}


def snapshot(*, equity='1000', last_equity='1000', positions=None):
    def get(host, path, key, secret, *, params=None, payload=None):
        assert payload is None, 'Risk checks must never place an order'
        if path == '/v2/account':
            return dict(status='ACTIVE', trading_blocked=False, account_blocked=False,
                        cash='1000', buying_power='1000', equity=equity,
                        last_equity=last_equity)
        if path == '/v2/positions':
            return positions or []
        if path == '/v2/orders':
            return []
        if path == '/v2/clock':
            return {'is_open': True}
        raise AssertionError(path)
    return get


@pytest.mark.parametrize('equity,previous,blocked', [
    ('990', '1000', True), ('989.99', '1000', True),
    ('990.01', '1000', False), ('1000', '1000', False),
])
def test_daily_loss_boundary(equity, previous, blocked):
    with patch.dict(os.environ, FLAGS, clear=True):
        reason = trader.broker_risk_check(now=NOW, key='k', secret='s',
                                         get=snapshot(equity=equity, last_equity=previous))
    assert bool(reason) == blocked
    if blocked:
        assert 'Daily account equity loss' in reason


@pytest.mark.parametrize('equity,blocked', [('500', False), ('499.99', True)])
def test_fixed_entry_equity_boundary(equity, blocked):
    with patch.dict(os.environ, FLAGS, clear=True):
        reason = trader.broker_risk_check(now=NOW, key='k', secret='s',
                                         get=snapshot(equity=equity, last_equity=equity))
    assert bool(reason) == blocked


@pytest.mark.parametrize('positions,blocked', [
    ([{'market_value': '190'}], False),
    ([{'market_value': '190.01'}], True),
    ([{'market_value': '100'}, {'market_value': '-100'}], True),
])
def test_gross_exposure_counts_shorts(positions, blocked):
    with patch.dict(os.environ, FLAGS, clear=True):
        reason = trader.broker_risk_check(now=NOW, key='k', secret='s',
                                         get=snapshot(positions=positions))
    assert bool(reason) == blocked


@pytest.mark.parametrize('field', ['equity', 'last_equity', 'market_value'])
@pytest.mark.parametrize('bad', [None, True, 'NaN', 'Infinity', 'invalid'])
def test_invalid_risk_evidence_fails_closed(field, bad):
    kwargs = {'positions': [{'market_value': bad}]} if field == 'market_value' else {field: bad}
    with patch.dict(os.environ, FLAGS, clear=True), pytest.raises(ValueError):
        trader.broker_risk_check(now=NOW, key='k', secret='s', get=snapshot(**kwargs))


def test_loss_before_scan_and_again_before_post():
    from zoneinfo import ZoneInfo
    decision = {'decision': 'READY', 'symbol': 'HD', 'notional_usd': '10.00',
                'client_order_id': trader.order_id(NOW.astimezone(ZoneInfo('America/New_York')).date(), 'HD')}
    with patch.dict(os.environ, FLAGS, clear=True):
        # A previously READY intent must be rejected when account risk changes.
        result = trader.execute(decision, key='k', secret='s', get=snapshot(equity='990'))
        assert result['decision'] == 'SKIP'
        result = trader.assess(now=NOW, key='k', secret='s', get=snapshot(equity='990'),
                                bars_fetch=lambda *a, **k: pytest.fail('Must block before scanning'))
        assert result['decision'] == 'SKIP'


@pytest.mark.parametrize('field', ['equity', 'last_equity'])
@pytest.mark.parametrize('bad', ['0', '-1'])
def test_nonpositive_equity_fails_closed(field, bad):
    with patch.dict(os.environ, FLAGS, clear=True), pytest.raises(ValueError):
        trader.broker_risk_check(now=NOW, key='k', secret='s', get=snapshot(**{field: bad}))


@pytest.mark.parametrize('mode,minimum_equity', [
    ('legacy', '500'), ('diversified', '500'),
    ('single', '5000'),
])
def test_allocation_modes_cannot_bypass_equity_limit(mode, minimum_equity):
    from decimal import Decimal
    with patch.dict(os.environ, {**FLAGS, 'PAPER_ALLOCATION_MODE': mode}, clear=True):
        assert trader.broker_risk_check(now=NOW, key='k', secret='s',
            get=snapshot(equity=minimum_equity, last_equity=minimum_equity)) is None
        smaller = str(Decimal(minimum_equity) - Decimal('0.01'))
        reason = trader.broker_risk_check(now=NOW, key='k', secret='s',
            get=snapshot(equity=smaller, last_equity=smaller))
        assert '2 percent' in reason


def test_pending_sell_does_not_release_exposure():
    base = snapshot(positions=[{'market_value': '200'}])
    def get(host, path, key, secret, **kwargs):
        if path == '/v2/orders':
            return [{'side': 'sell', 'status': 'accepted', 'notional': '200'}]
        return base(host, path, key, secret, **kwargs)
    with patch.dict(os.environ, FLAGS, clear=True):
        reason = trader.broker_risk_check(now=NOW, key='k', secret='s', get=get)
    assert 'gross exposure' in reason
