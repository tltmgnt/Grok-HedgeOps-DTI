from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import json
import os
import tempfile
from pathlib import Path
import pytest

import autonomous_paper_session as session
from paper_opportunity_intelligence import fresh_quote, PAPER, DATA

NOW = datetime(2026, 11, 9, 16, tzinfo=timezone.utc)


def lot(value='100', age=0):
    opened = NOW - timedelta(days=age)
    position = dict(symbol='SPY', side='long', qty='1', qty_available='1',
                    cost_basis='100', market_value=value)
    order = dict(id='entry-1', symbol='SPY', side='buy', status='filled',
                 filled_qty='1', filled_at=opened.isoformat(), submitted_at=opened.isoformat(),
                 client_order_id=f'hedgeopsauto-{opened:%Y%m%d}-spy')
    return position, [order]


@pytest.mark.parametrize('value,age,reason', [
    ('97', 0, 'LOSS_3_PERCENT'), ('106', 0, 'PROFIT_6_PERCENT'),
    ('100', 5, 'HOLDING_5_CALENDAR_DAYS'), ('100', 4, None)])
def test_exit_thresholds(value, age, reason):
    p, orders = lot(value, age)
    plan = session.exit_plan(p, orders, now=NOW)
    assert (plan['reason'] if plan else None) == reason


@pytest.mark.parametrize('mutate', [
    lambda p, o: o[0].update(client_order_id='manual'),
    lambda p, o: p.update(qty='2', qty_available='2'),
    lambda p, o: p.update(qty_available='0'),
    lambda p, o: o[0].update(status='partially_filled'),
    lambda p, o: p.update(side='short'),
    lambda p, o: o.append(dict(id='open', symbol='SPY', side='sell', status='new', filled_qty='0')),
])
def test_ambiguous_or_manual_positions_never_exit(mutate):
    p, orders = lot('90')
    mutate(p, orders)
    assert session.exit_plan(p, orders, now=NOW) is None


def quote_get(*args, **kwargs):
    assert args[0] == DATA
    return {'quote': {'t': NOW.isoformat(), 'bp': 99.9, 'ap': 100.1}}


def test_quote_and_feed():
    with patch.dict(os.environ, {'PAPER_DATA_FEED': 'sip'}):
        def get(*a, **kw):
            assert kw['params'] == {'feed': 'sip'}
            return quote_get(*a, **kw)
        assert fresh_quote('SPY', 'k', 's', now=NOW, get=get)['feed'] == 'sip'


@pytest.mark.parametrize('q', [
    {'t': (NOW-timedelta(minutes=3)).isoformat(), 'bp': 100, 'ap': 100},
    {'t': (NOW+timedelta(seconds=1)).isoformat(), 'bp': 100, 'ap': 100},
    {'t': NOW.isoformat(), 'bp': 0, 'ap': 100},
    {'t': NOW.isoformat(), 'bp': 100, 'ap': 99},
    {'t': NOW.isoformat(), 'bp': 99, 'ap': 101},
    {'t': NOW.isoformat(), 'bp': 'NaN', 'ap': 100},
])
def test_unsafe_quotes_fail_closed(q):
    with pytest.raises(ValueError):
        fresh_quote('SPY', 'k', 's', now=NOW, get=lambda *a, **k: {'quote': q})


def test_monitor_only_never_posts():
    p, orders = lot('90')
    def get(host, path, *a, **kw):
        assert host == PAPER
        assert 'payload' not in kw
        return orders if path == '/v2/orders' else [p]
    with patch.dict(os.environ, {'PAPER_AUTO_TRADING_ENABLED': 'true', 'PAPER_AUTO_KILL_SWITCH': 'false'}):
        result = session.manage_exits('k', 's', now=NOW, get=get, monitor_only=True)
    assert result[0]['decision'] == 'MONITOR_EXIT'


def test_partial_exit_acknowledgment_not_retried():
    p, orders = lot('90')
    posts = []
    def get(host, path, *a, **kw):
        if kw.get('payload'):
            posts.append(kw['payload'])
            raise RuntimeError('Timeout')
        if path == '/v2/orders:by_client_order_id':
            raise RuntimeError('Alpaca HTTP 404')
        if path == '/v2/orders': return orders
        if path == '/v2/positions': return [p]
        if path == '/v2/clock': return {'is_open': True}
        if path == '/v2/account': return {'status': 'ACTIVE', 'trading_blocked': False, 'account_blocked': False}
        raise AssertionError(path)
    with patch.dict(os.environ, {'PAPER_AUTO_TRADING_ENABLED': 'true', 'PAPER_AUTO_KILL_SWITCH': 'false'}):
        with patch.object(session, 'fresh_quote'), patch.object(session, 'datetime') as dt:
            dt.now.return_value = NOW
            dt.fromisoformat.side_effect = datetime.fromisoformat
            with pytest.raises(RuntimeError): session.manage_exits('k', 's', now=NOW, get=get)
    assert len(posts) == 1
    assert posts[0]['side'] == 'sell'
    assert posts[0]['qty'] == '1'


def test_history_pagination_overlap():
    batch = [dict(id=str(i), submitted_at=NOW.isoformat()) for i in range(500)]
    responses = iter([batch, [batch[-1], dict(id='last', submitted_at=NOW.isoformat())]])
    assert len(session.order_history('k', 's', get=lambda *a, **k: next(responses))) == 501


def test_repeated_history_fails():
    batch = [dict(id=str(i), submitted_at=NOW.isoformat()) for i in range(500)]
    with pytest.raises(ValueError, match='no progress'):
        session.order_history('k', 's', get=lambda *a, **k: batch)


def test_performance_scope_and_drawdown():
    result = session.performance({'timestamp': [1, 2, 3], 'equity': [100, 120, 90]})
    assert float(result['account_equity_drawdown_pct']) == 25
    assert float(result['account_equity_change_pct']) == -10
    assert 'not strategy alpha' in result['scope']


def test_missing_credentials_writes_failure_evidence():
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {}, clear=True):
        assert session.main(['--output-dir', tmp]) == 1
        assert json.loads((Path(tmp)/'session.json').read_text())['status'] == 'ERROR'
        assert (Path(tmp)/'summary.md').exists()


def test_market_closed_does_not_trade():
    def get(host, path, *a, **kw):
        assert 'payload' not in kw
        return {'is_open': False} if path == '/v2/clock' else {'equity': [], 'timestamp': []}
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'ALPACA_API_KEY': 'k', 'ALPACA_API_SECRET': 's', 'PAPER_REQUIRE_FRESH_QUOTE': 'true'}):
        with patch.object(session, 'request_json', side_effect=get), patch.object(session, 'entry_main') as entry:
            assert session.main(['--output-dir', tmp]) == 0
        entry.assert_not_called()


def test_worker_stops_after_error_without_retry():
    import paper_research_worker as worker
    with tempfile.TemporaryDirectory() as tmp, patch.object(worker, 'session_main', return_value=1) as run:
        with patch.object(worker.time, 'sleep', side_effect=AssertionError('No retry')):
            assert worker.main(['--output-dir', tmp]) == 1
    run.assert_called_once()


def test_exit_intent_saved_before_ambiguous_post():
    p, orders = lot('90')
    audits = []
    def get(host, path, *a, **kw):
        if kw.get('payload'):
            assert audits[0]['intent'] == kw['payload']
            raise RuntimeError('Ambiguous')
        if path == '/v2/orders': return orders
        if path == '/v2/positions': return [p]
        if path == '/v2/clock': return {'is_open': True}
        if path == '/v2/account': return {'status': 'ACTIVE', 'trading_blocked': False, 'account_blocked': False}
        raise AssertionError(path)
    with patch.dict(os.environ, {'PAPER_AUTO_TRADING_ENABLED': 'true', 'PAPER_AUTO_KILL_SWITCH': 'false'}):
        with patch.object(session, 'fresh_quote'), patch.object(session, 'datetime') as dt:
            dt.now.return_value = NOW
            dt.fromisoformat.side_effect = datetime.fromisoformat
            with pytest.raises(RuntimeError):
                session.manage_exits('k', 's', now=NOW, get=get, audit=audits.append)
    assert len(audits) == 1


def test_full_session_http_contract_buy_reconcile_and_exit():
    """Exercise real session/entry/exit code against an in-memory paper HTTP server."""
    from io import BytesIO
    from urllib.error import HTTPError
    from urllib.parse import urlsplit, parse_qs
    from paper_opportunity_intelligence import DATA
    from stock_discovery import DEFAULT_SYMBOLS
    current = datetime.now(timezone.utc)
    orders, positions, posts = [], [], []

    def respond(req, timeout=None):
        url = urlsplit(req.full_url)
        assert url.netloc in ('paper-api.alpaca.markets', 'data.alpaca.markets')
        path = url.path
        query = parse_qs(url.query)
        if req.method == 'POST':
            assert url.netloc == 'paper-api.alpaca.markets'
            payload = json.loads(req.data)
            posts.append(payload)
            result = dict(payload, id=f'paper-{len(posts)}', status='accepted',
                          submitted_at=current.isoformat(), filled_qty='0')
            orders.append(result)
        elif path == '/v2/account/portfolio/history':
            result = {'timestamp': [1, 2], 'equity': [1000, 1001]}
        elif path == '/v2/account':
            result = {'status': 'ACTIVE', 'trading_blocked': False, 'account_blocked': False,
                      'cash': '1000', 'buying_power': '1000', 'equity': '1000', 'last_equity': '1000'}
        elif path == '/v2/clock': result = {'is_open': True}
        elif path == '/v2/positions': result = positions
        elif path == '/v2/orders':
            result = [o for o in orders if o['status'] != 'filled'] if query.get('status') == ['open'] else orders
        elif path == '/v2/orders:by_client_order_id':
            raise HTTPError(req.full_url, 404, 'Not found', {}, None)
        elif path == '/v2/assets/HD':
            result = {'status': 'active', 'tradable': True, 'fractionable': True}
        elif path == '/v2/stocks/HD/quotes/latest':
            result = {'quote': {'t': current.isoformat(), 'bp': '9.99', 'ap': '10.01'}}
        elif path == '/v2/stocks/bars': result = {'bars': {s: [] for s in DEFAULT_SYMBOLS}}
        elif path == '/v1beta1/news':
            result = {'news': [{'symbols': ['HD'], 'headline': 'HD earnings results',
                                'created_at': current.isoformat()}]}
        else: raise AssertionError(path)
        return BytesIO(json.dumps(result).encode())

    from test_paper_opportunity_intelligence import candidate
    report = {'candidates': [candidate(last_bar_utc=(current-timedelta(days=1)).isoformat())]}
    env = {'ALPACA_API_KEY': 'paper-test', 'ALPACA_API_SECRET': 'paper-test-secret',
           'PAPER_AUTO_TRADING_ENABLED': 'true', 'PAPER_AUTO_KILL_SWITCH': 'false',
           'PAPER_ALLOCATION_MODE': 'legacy', 'PAPER_REQUIRE_FRESH_QUOTE': 'true'}
    with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env, clear=True):
        with patch('urllib.request.build_opener') as opener, patch('paper_opportunity_intelligence.build_report', return_value=report):
            opener.return_value.open.side_effect = respond
            assert session.main(['--output-dir', str(Path(tmp)/'monitor'), '--monitor-only']) == 0
            assert posts == []
            assert session.main(['--output-dir', str(Path(tmp)/'buy')]) == 0
            assert len(posts) == 1 and posts[0]['side'] == 'buy'
            assert session.main(['--output-dir', str(Path(tmp)/'pending')]) == 0
            assert len(posts) == 1  # Acknowledgment is pending, no duplicate.
            orders[0].update(status='filled', filled_qty='1', filled_at=current.isoformat())
            positions.append(dict(symbol='HD', side='long', qty='1', qty_available='1',
                                  cost_basis='10', market_value='9'))
            assert session.main(['--output-dir', str(Path(tmp)/'exit')]) == 0
            assert len(posts) == 2 and posts[1]['side'] == 'sell'
            assert posts[1]['qty'] == '1'
            assert session.main(['--output-dir', str(Path(tmp)/'exit-pending')]) == 0
            assert len(posts) == 2
            assert (Path(tmp)/'exit'/'exit-intents.jsonl').exists()
