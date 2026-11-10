"""Bounded paper-only limit entries for reviewed investment horizon research."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
import os
from zoneinfo import ZoneInfo

from investment_research import HORIZONS, evaluate, fingerprint, validate
from paper_opportunity_intelligence import (PAPER, allocation_policy, broker_risk_check,
                                           fresh_quote, money, request_json)

PREFIX = 'ho-invest'
BUDGET = Decimal('10.00')


def enabled():
    return (os.getenv('INVESTMENT_PAPER_ENABLED') == 'true'
            and os.getenv('PAPER_AUTO_TRADING_ENABLED') == 'true'
            and os.getenv('PAPER_AUTO_KILL_SWITCH') == 'false')


def execute_one(policy, horizon, *, key, secret, get=request_json, clock=None, audit=None):
    """Recompute from policy and current provider evidence; never accept READY input.

    At most one POST per call, no retries. Own IDs keep these lots outside the
    momentum strategy's five-day exit rule. Holdings require quarterly review;
    this module does not automatically sell or average down.
    """
    validate(policy)
    if horizon not in HORIZONS:
        raise ValueError('Invalid horizon')
    result = {'mode': 'PAPER_ONLY', 'decision': 'SKIP', 'horizon': horizon,
              'strategy_version': policy['version'], 'policy_sha256': fingerprint(policy)}
    def skip(reason):
        return dict(result, reason=reason)
    if not enabled():
        return skip('Paper investment execution disabled or kill switch active')
    if allocation_policy() != ('legacy', BUDGET, 1):
        return skip('Investment paper entries require fixed legacy allocation')
    if not key or not secret:
        return skip('Paper credentials not configured')
    clock = clock or (lambda: datetime.now(timezone.utc))
    audit = audit or (lambda event: None)
    now = clock()
    market = get(PAPER, '/v2/clock', key, secret)
    if not isinstance(market, dict) or market.get('is_open') is not True:
        return skip('Market closed or clock unavailable')
    for row in policy['candidates']:
        quote = fresh_quote(row['symbol'], key, secret, now=clock(), get=get)
        decision = evaluate(row, horizon, quote, now=clock())
        if decision['status'] != 'REVIEW_READY':
            continue
        symbol = row['symbol']
        today = now.astimezone(ZoneInfo('America/New_York')).date()
        client_id = f'{PREFIX}-{today:%Y%m%d}-{horizon}-{symbol.lower()}'
        # Resolve this deterministic ID before considering a second POST.
        try:
            existing = get(PAPER, '/v2/orders:by_client_order_id', key, secret,
                           params={'client_order_id': client_id})
        except RuntimeError as exc:
            if str(exc) != 'Alpaca HTTP 404':
                raise
        else:
            if not isinstance(existing, dict) or not existing.get('id'):
                raise ValueError('Existing order response unavailable')
            return dict(result, decision='ALREADY_EXISTS', broker_status=existing.get('status'),
                        reason='Reconcile existing order; never duplicate')
        reason = broker_risk_check(now=clock(), key=key, secret=secret, get=get)
        if reason:
            return skip(reason)
        positions = get(PAPER, '/v2/positions', key, secret)
        if not isinstance(positions, list) or any(not isinstance(p, dict) for p in positions):
            raise ValueError('Positions unavailable')
        if any(p.get('symbol') == symbol for p in positions):
            return skip('Existing holding; no automatic averaging down')
        orders = get(PAPER, '/v2/orders', key, secret,
                     params={'status': 'all', 'limit': 500, 'direction': 'desc'})
        if not isinstance(orders, list) or len(orders) >= 500 or any(not isinstance(o, dict) for o in orders):
            raise ValueError('Order history unavailable or truncated')
        if any(str(o.get('client_order_id', '')).startswith(f'{PREFIX}-{today:%Y%m%d}-') for o in orders):
            return skip('One investment paper attempt per trading day across both horizons')
        asset = get(PAPER, '/v2/assets/' + symbol, key, secret)
        if (not isinstance(asset, dict) or asset.get('status') != 'active'
                or asset.get('tradable') is not True or asset.get('fractionable') is not True):
            return skip('Asset not confirmed active tradable and fractionable')
        # Final quote must still pass value, freshness, spread and thesis gates.
        decision = evaluate(row, horizon, fresh_quote(symbol, key, secret, now=clock(), get=get), now=clock())
        if decision['status'] != 'REVIEW_READY':
            return skip('Research gates changed before submission')
        cap = Decimal(decision['limit_price_cap']).quantize(Decimal('.01'), rounding=ROUND_DOWN)
        if cap <= 0:
            return skip('Invalid limit price')
        market = get(PAPER, '/v2/clock', key, secret)
        if (not isinstance(market, dict) or market.get('is_open') is not True or not enabled()
                or allocation_policy() != ('legacy', BUDGET, 1)):
            return skip('Market closed or execution disabled before submission')
        payload = {'symbol': symbol, 'notional': str(BUDGET), 'side': 'buy', 'type': 'limit',
                   'limit_price': str(cap), 'time_in_force': 'day', 'client_order_id': client_id}
        audit({'event': 'PAPER_ENTRY_INTENT', 'policy_sha256': fingerprint(policy),
               'horizon': horizon, 'assessment': decision, 'order': payload})
        try:
            order = get(PAPER, '/v2/orders', key, secret, payload=payload)
        except (RuntimeError, OSError, ValueError, TypeError):
            return dict(result, decision='UNKNOWN_RECONCILE',
                        reason='Submission outcome uncertain; inspect broker by client order ID before retrying')
        try:
            valid_ack = (isinstance(order, dict) and bool(order.get('id'))
                and all(order.get(k) == payload[k] for k in ('symbol', 'side', 'type', 'time_in_force', 'client_order_id'))
                and money(order.get('notional')) == BUDGET and money(order.get('limit_price')) == cap
                and isinstance(order.get('status'), str))
            if valid_ack and order['status'] == 'filled':
                valid_ack = money(order.get('filled_qty')) > 0 and 0 < money(order.get('filled_avg_price')) <= cap
        except (ValueError, TypeError):
            valid_ack = False
        if not valid_ack:
            return dict(result, decision='UNKNOWN_RECONCILE', reason='Ambiguous acknowledgment; reconcile broker')
        return dict(result, decision='SUBMITTED', symbol=symbol, client_order_id=client_id,
                    broker_status=order.get('status'), order_filled=order.get('status') == 'filled',
                    limit_price=str(cap), notional_usd=str(BUDGET),
                    holding_review='Quarterly and at material events; no automatic horizon sale')
    return skip('No candidate passed current valuation and financial review gates')
