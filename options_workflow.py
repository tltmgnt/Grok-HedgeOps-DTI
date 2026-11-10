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
    # Require an unambiguous ISO date; fromisoformat also accepts compact
    # forms that are easy to misread in a manual order workflow.
    if not isinstance(expiration, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', expiration):
        raise ValueError('Expiration must be YYYY-MM-DD')
    try:
        expiry = date.fromisoformat(expiration)
        s, p = Decimal(str(strike)), Decimal(str(limit_price))
    except (ValueError, InvalidOperation) as exc:
        raise ValueError('Invalid expiry, strike, or limit price') from exc
    if expiry < date.today() or not s.is_finite() or not p.is_finite():
        raise ValueError('Expired contract or non-finite price')
    # OCC option symbols encode only a two-digit expiration year. Restrict
    # the planner horizon so a century-different date cannot alias the same
    # encoded symbol, and reject implausibly distant manual expirations.
    if (expiry.year - date.today().year > 5
            or (expiry.year - date.today().year == 5
                and (expiry.month, expiry.day) > (date.today().month, date.today().day))):
        raise ValueError('Expiration exceeds five-year planner horizon')
    # Bound the manual input to avoid nonsensical exposure estimates and
    # oversized Decimal arithmetic. These are planner limits, not a claim
    # about broker-supported contracts or executable prices.
    if s > Decimal('1000000') or p > Decimal('1000000'):
        raise ValueError('Strike or limit exceeds planner safety bound')
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
    # Estimates assume standard 100-share equity-option contracts. Adjusted
    # contracts and other multipliers require broker contract metadata and
    # cannot safely be planned from symbol/strike/expiry alone.
    multiplier = 100
    premium = p * contracts * multiplier
    cash_to_secure_put = s * contracts * multiplier
    covered_shares = contracts * multiplier
    if action in ('buy_call', 'buy_put'):
        max_loss = premium
    elif action in ('sell_put', 'cash_secured_put'):
        # Conservative gross assignment exposure; premium is excluded.
        max_loss = cash_to_secure_put
    else:
        max_loss = None  # Depends on owned shares and entry cost.
    return {
        'action': action, 'mode': mode, 'symbol': symbol,
        'expiration': expiry.isoformat(), 'strike': str(s),
        'contracts': contracts, 'limit_price': str(p),
        'estimated_premium_usd': str(premium),
        'estimated_max_loss_usd': str(max_loss) if max_loss is not None else None,
        'cash_secured_put_collateral_usd': (
            str(cash_to_secure_put) if action in ('sell_put', 'cash_secured_put') else None
        ),
        'covered_call_shares_required': (
            covered_shares if action in ('sell_call', 'covered_call') else None
        ),
        'risk_estimates_are_broker_verified': False,
        'assumed_contract_multiplier': multiplier,
        'contract_terms_verified': False,
        'contract_warning': (
            'Estimates assume a standard 100-share contract. Adjusted '
            'deliverables, contract multiplier, option availability, and '
            'exercise style must be verified from broker contract metadata '
            'before any PAPER or live execution.'
        ),
        'status': 'VALIDATED_PLAN_ONLY',
        'broker_order_submitted': False,
        'warning': 'No options orders are sent by this workflow. '
                   'Paper/live execution requires durable idempotency, '
                   'broker permissions, collateral and position checks.'
    }



def verify_standard_contract(plan_result, contract):
    """Cross-check broker-sourced contract metadata; never submit an order.

    Only standard 100-share US equity options are supported. Missing or
    conflicting metadata must not silently inherit the planner's assumption.
    """
    if not isinstance(plan_result, dict) or plan_result.get('status') != 'VALIDATED_PLAN_ONLY':
        raise ValueError('Expected a validated options plan')
    # A caller-supplied dict is not evidence of a validated order. Reject
    # tampered plans before comparing contract metadata.
    expected = plan(
        plan_result.get('action'), plan_result.get('mode'),
        plan_result.get('symbol'), plan_result.get('expiration'),
        plan_result.get('strike'), plan_result.get('contracts'),
        plan_result.get('limit_price'),
        approval=('I_APPROVE_LIVE_OPTIONS'
                  if plan_result.get('mode') == 'live' else ''),
        collateral_verified=True, position_verified=True,
    )
    if any(plan_result.get(field) != expected[field] for field in (
            'action', 'mode', 'symbol', 'expiration', 'strike', 'contracts',
            'limit_price', 'estimated_premium_usd', 'estimated_max_loss_usd',
            'cash_secured_put_collateral_usd', 'covered_call_shares_required',
            'assumed_contract_multiplier', 'risk_estimates_are_broker_verified',
            'contract_terms_verified', 'broker_order_submitted')):
        raise ValueError('Options plan fields are inconsistent or tampered')
    if not isinstance(contract, dict):
        raise ValueError('Broker contract metadata required')
    action = plan_result['action']
    expected_type = 'call' if action in ('buy_call', 'sell_call', 'covered_call') else 'put'
    if action not in ('buy_call', 'buy_put', 'sell_call', 'sell_put',
                      'covered_call', 'cash_secured_put'):
        raise ValueError('Unsupported contract action')
    if (contract.get('underlying_symbol') != plan_result['symbol']
            or contract.get('expiration_date') != plan_result['expiration']
            or contract.get('type') != expected_type):
        raise ValueError('Broker contract identity mismatch')
    try:
        strike = Decimal(str(contract['strike_price']))
        multiplier = Decimal(str(contract['multiplier']))
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError('Broker contract terms missing or invalid') from exc
    if not strike.is_finite() or strike != Decimal(plan_result['strike']):
        raise ValueError('Broker contract strike mismatch')
    if not multiplier.is_finite() or multiplier != 100:
        raise ValueError('Adjusted or nonstandard contract requires separate review')
    # OCC-style option symbol must independently encode the same underlying,
    # expiration, right and strike. Merely checking the metadata fields would
    # allow a conflicting contract symbol to pass.
    option_symbol = contract.get('symbol')
    if not isinstance(option_symbol, str):
        raise ValueError('Broker option contract symbol missing or invalid')
    match = re.fullmatch(r'([A-Z][A-Z0-9.]{0,5}) *([0-9]{6})([CP])([0-9]{8})',
                         option_symbol)
    if match is None:
        raise ValueError('Broker option contract symbol missing or invalid')
    root, yymmdd, right, strike_code = match.groups()
    expected_right = 'C' if expected_type == 'call' else 'P'
    if (root != plan_result['symbol']
            or yymmdd != plan_result['expiration'][2:4]
                         + plan_result['expiration'][5:7]
                         + plan_result['expiration'][8:10]
            or right != expected_right
            or Decimal(int(strike_code)) / 1000 != strike):
        raise ValueError('Option contract symbol conflicts with contract metadata')
    # Verification is only as trustworthy as the supplied broker metadata.
    # Do not mark it broker-verified without an authenticated source.
    return {
        'contract_symbol': contract['symbol'],
        'contract_multiplier': 100,
        'contract_matches_plan': True,
        'broker_source_authenticated': False,
        'broker_order_submitted': False,
        'status': 'CONTRACT_MATCHED_OFFLINE_ONLY',
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
