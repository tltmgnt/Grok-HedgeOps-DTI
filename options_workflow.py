"""Validate manual options workflow intent. No broker network calls.

Live execution is deliberately not wired into CI: this module only validates
and describes an order; execution requires a separately reviewed durable
options-specific ledger and broker risk checks.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import argparse
import json
import re

ACTIONS = ('buy_call', 'buy_put', 'sell_call', 'sell_put',
           'covered_call', 'cash_secured_put', 'close', 'roll', 'reconcile')
MODES = ('simulate', 'paper', 'live')


def plan(action, mode, symbol, expiration, strike, contracts, limit_price,
         *, approval='', collateral_verified=False, position_verified=False):
    if action not in ACTIONS or mode not in MODES:
        raise ValueError('Unknown options action or mode')
    if not re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', symbol):
        raise ValueError('Invalid underlying symbol')
    try:
        expiry = date.fromisoformat(expiration)
        s, p = Decimal(str(strike)), Decimal(str(limit_price))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError('Invalid expiry, strike, or limit price') from exc
    if expiry < date.today() or not s.is_finite() or not p.is_finite():
        raise ValueError('Expired contract or non-finite price')
    if s <= 0 or p <= 0 or s.as_tuple().exponent < -2 or p.as_tuple().exponent < -2:
        raise ValueError('Strike and limit must be positive with at most 2 decimals')
    if type(contracts) is not int or not 1 <= contracts <= 100:
        raise ValueError('Contracts must be an integer from 1 to 100')
    # No naked short calls. Covered calls require verified shares; short
    # puts require verified cash collateral. Fail closed on missing evidence.
    if action in ('sell_call', 'covered_call') and not position_verified:
        raise ValueError('Short calls require verified covered shares')
    if action in ('sell_put', 'cash_secured_put') and not collateral_verified:
        raise ValueError('Short puts require verified cash collateral')
    if action in ('close', 'roll', 'reconcile'):
        raise ValueError('Position lifecycle actions require verified existing order/position')
    if mode == 'live' and approval != 'I_APPROVE_LIVE_OPTIONS':
        raise ValueError('Live options mode requires explicit approval phrase')
    return {
        'action': action, 'mode': mode, 'symbol': symbol,
        'expiration': expiry.isoformat(), 'strike': str(s),
        'contracts': contracts, 'limit_price': str(p),
        'estimated_premium_usd': str(p * contracts * 100),
        'status': 'VALIDATED_PLAN_ONLY',
        'broker_order_submitted': False,
        'warning': 'No options orders are sent by this workflow. '
                   'Paper/live execution requires durable idempotency, '
                   'broker permissions, collateral and position checks.'
    }


def main():
    parser = argparse.ArgumentParser()
    for field in ('action', 'mode', 'symbol', 'expiration', 'strike', 'limit_price'):
        parser.add_argument('--' + field.replace('_', '-'), required=True)
    parser.add_argument('--contracts', type=int, required=True)
    parser.add_argument('--approval', default='')
    parser.add_argument('--collateral-verified', action='store_true')
    parser.add_argument('--position-verified', action='store_true')
    args = parser.parse_args()
    print(json.dumps(plan(args.action, args.mode, args.symbol, args.expiration,
                          args.strike, args.contracts, args.limit_price,
                          approval=args.approval,
                          collateral_verified=args.collateral_verified,
                          position_verified=args.position_verified), indent=2))


if __name__ == '__main__':
    main()
