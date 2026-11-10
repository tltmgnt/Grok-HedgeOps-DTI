"""Read-only scenario research for two holding periods; never a buy recommendation."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re

HORIZONS = {"1-2y": 2, "5y": 5}
CHECKS = ("annual_earnings_reconciled", "cash_flow_reviewed", "debt_reviewed",
          "dilution_reviewed", "thesis_intact")


def number(value, *, minimum=Decimal('0'), maximum=Decimal('1000000')):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a financial number')
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation):
        raise ValueError('Invalid financial number') from None
    if not result.is_finite() or not minimum <= result <= maximum:
        raise ValueError('Financial number out of range')
    return result


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be text')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def fingerprint(policy):
    return hashlib.sha256(json.dumps(policy, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate(policy):
    if policy.get('version') != 'investment-horizons-v1':
        raise ValueError('Unsupported policy')
    rows = policy.get('candidates')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError('One to twenty candidates required')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('symbol'), str)
                or not re.fullmatch(r'[A-Z]{1,5}', row['symbol'])):
            raise ValueError('Invalid stock symbol')
        if row['symbol'] in seen:
            raise ValueError('Duplicate symbol')
        seen.add(row['symbol'])
        if not isinstance(row.get('review'), dict) or not isinstance(row.get('horizons'), dict):
            raise ValueError('Review and horizons must be objects')
        if number(row['starting_eps']) <= 0:
            raise ValueError('Positive EPS required')
        for horizon in HORIZONS:
            model = row['horizons'][horizon]
            low, high = map(number, model['entry_zone'])
            if not 0 < low <= high:
                raise ValueError('Invalid entry zone')
            number(model['required_return'], maximum=Decimal('1'))
            for name in ('bear', 'base', 'bull'):
                scenario = model[name]
                number(scenario['growth'], minimum=Decimal('-.9'), maximum=Decimal('1'))
                if number(scenario['pe'], maximum=Decimal('100')) <= 0:
                    raise ValueError('Positive PE required')
    return policy


def evaluate(row, horizon, quote, *, now):
    """Record independent gates; price falling alone never releases an entry."""
    model = row['horizons'][horizon]
    years = HORIZONS[horizon]
    eps = number(row['starting_eps'])
    values = {name: eps * (1 + number(model[name]['growth'], minimum=Decimal('-.9'))) ** years
              * number(model[name]['pe']) for name in ('bear', 'base', 'bull')}
    if not values['bear'] <= values['base'] <= values['bull']:
        raise ValueError('Scenario values must be ordered')
    ceiling = values['base'] / (1 + number(model['required_return'])) ** years
    low, high = map(number, model['entry_zone'])
    cap = min(high, ceiling)
    gates = []
    price = None
    try:
        stamp = timestamp(quote['timestamp'])
        bid, ask = number(quote['bid']), number(quote['ask'])
        if not (timedelta(0) <= now - stamp <= timedelta(seconds=120)
                and 0 < bid <= ask and (ask-bid)/((ask+bid)/2) <= Decimal('.005')):
            raise ValueError('Quote freshness or spread failed')
        price = ask  # Entry uses the executable side, never a cheaper midpoint.
    except (KeyError, TypeError, ValueError):
        gates.append('CURRENT_QUOTE_REQUIRED')
    review = row.get('review', {})
    try:
        reviewed = timestamp(review['reviewed_at'])
        if not timedelta(0) <= now - reviewed <= timedelta(days=90):
            gates.append('QUARTERLY_REVIEW_DUE')
        source_at = timestamp(review['financials_as_of'])
        if not timedelta(0) <= now - source_at <= timedelta(days=180):
            gates.append('CURRENT_FINANCIALS_REQUIRED')
        if not isinstance(review.get('sources'), list) or not review['sources'] or any(
                not isinstance(s, str) or not s.startswith('https://') for s in review['sources']):
            gates.append('FINANCIAL_SOURCES_REQUIRED')
    except (KeyError, TypeError, ValueError):
        gates.append('DATED_FINANCIAL_REVIEW_REQUIRED')
    if row.get('eps_basis') != 'reviewed_annual':
        gates.append('ILLUSTRATIVE_EPS_NOT_EXECUTABLE')
    for check in CHECKS:
        if review.get(check) is not True:
            gates.append(check.upper() + '_REQUIRED')
    if price is not None and not low <= price <= cap:
        gates.append('PRICE_OUTSIDE_ENTRY_ZONE')
    status = 'REVIEW_READY' if not gates else ('WATCH' if gates == ['PRICE_OUTSIDE_ENTRY_ZONE'] else 'EVIDENCE_REQUIRED')
    return {'symbol': row['symbol'], 'horizon': horizon, 'model_years': years,
            'status': status, 'failed_gates': gates, 'observed_at_utc': now.isoformat(),
            'quote': quote, 'entry_zone': [str(low), str(high)],
            'entry_ceiling': str(ceiling), 'limit_price_cap': str(cap),
            'scenario_values': {k: str(v.quantize(Decimal('.01'))) for k, v in values.items()},
            'scenario_price_returns_pct': {k: str(((v/price-1)*100).quantize(Decimal('.01')))
                                           for k, v in values.items()} if price else None,
            'eps_basis': row.get('eps_basis'), 'review': review,
            'order_authority': False}


def build_report(policy, quotes, *, now, origin='PROVIDER_SNAPSHOT'):
    validate(policy)
    return {'strategy_version': policy['version'], 'policy_sha256': fingerprint(policy),
            'generated_at_utc': now.isoformat(), 'origin': origin, 'order_authority': False,
            'limitations': 'Scenario assumptions, not forecasts. No dividends, taxes or fees. Two year model is not a one year exit forecast.',
            'assessments': [evaluate(row, h, quotes.get(row['symbol']), now=now)
                            for row in policy['candidates'] for h in HORIZONS]}


def collect_quotes(policy, *, key, secret, clock=None, get=None):
    # Local import keeps the pure research evaluator independent of broker code.
    from paper_opportunity_intelligence import fresh_quote, request_json
    clock = clock or (lambda: datetime.now(timezone.utc))
    get = get or request_json
    if not key or not secret:
        return {}, ['MARKET_DATA_NOT_CONFIGURED']
    quotes, errors = {}, []
    for row in policy['candidates']:
        try:
            quotes[row['symbol']] = fresh_quote(row['symbol'], key, secret, now=clock(), get=get)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError):
            errors.append(row['symbol'] + ': QUOTE_UNAVAILABLE')
    return quotes, errors


def save_report(report, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / 'research.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    lines = ['# Investment horizon research', '', 'Research only. Review readiness is not a fill or permission to trade.',
             '', '| Symbol | Horizon | Status | Failed gates |', '| --- | --- | --- | --- |']
    for row in report.get('assessments', []):
        lines.append(f"| {row['symbol']} | {row['horizon']} | {row['status']} | {', '.join(row['failed_gates']) or 'None'} |")
    lines.extend(['', 'Configuration and data: ' + ', '.join(report.get('data_errors', [])),
                  '', 'Paper execution: ' + report.get('execution', {}).get('decision', 'NOT_REQUESTED')])
    (output / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, default=Path('research/investment_policy.json'))
    parser.add_argument('--output', type=Path, default=Path('investment-output'))
    parser.add_argument('--paper-entry', action='store_true')
    parser.add_argument('--horizon', choices=HORIZONS, default='1-2y')
    args = parser.parse_args(argv)
    report = {'assessments': [], 'order_authority': False, 'data_errors': []}
    code = 0
    try:
        policy = validate(json.loads(args.policy.read_text(encoding='utf-8')))
        key, secret = os.getenv('ALPACA_API_KEY', ''), os.getenv('ALPACA_API_SECRET', '')
        quotes, errors = collect_quotes(policy, key=key, secret=secret)
        report = build_report(policy, quotes, now=datetime.now(timezone.utc))
        report['data_errors'] = errors
        code = 1 if errors else 0
        if args.paper_entry:
            args.output.mkdir(parents=True, exist_ok=True)
            from investment_paper_execution import execute_one
            with (args.output / 'entry-intents.jsonl').open('a', encoding='utf-8') as journal:
                def audit(event):
                    journal.write(json.dumps(event, allow_nan=False) + '\n')
                    journal.flush()
                    os.fsync(journal.fileno())
                report['execution'] = execute_one(policy, args.horizon, key=key, secret=secret, audit=audit)
            if report['execution']['decision'] == 'UNKNOWN_RECONCILE':
                code = 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ArithmeticError):
        # Never publish raw provider errors, account records or input text.
        report['data_errors'] = ['RESEARCH_UNAVAILABLE_CHECK_POLICY_AND_PROVIDER']
        code = 1
    save_report(report, args.output)
    print('Investment research report saved; order results require broker reconciliation.')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
