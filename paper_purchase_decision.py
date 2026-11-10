"""Always record/analyze a manual paper decision; optionally submit to PAPER only.

Analysis and optional reference-price simulation survive missing credentials,
closed markets, broker rejection and ambiguous submissions. Never claim a fill.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import re

from paper_opportunity_intelligence import PAPER, DATA, money, request_json
from stock_discovery import fetch_bars, build_report


def validate(symbol, notional, request_id):
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z][A-Z0-9.]{0,14}', symbol):
        raise ValueError('Use an uppercase stock ticker')
    amount = money(notional)
    if not Decimal('1') <= amount <= Decimal('200') or amount != amount.quantize(Decimal('.01')):
        raise ValueError('Paper purchase must be $1–$200 in whole cents')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,48}', request_id):
        raise ValueError('A stable request ID of 8–48 letters, digits, underscores or hyphens is required')
    return amount


def analyze(symbol, *, thesis='', reference_price=None, key='', secret='', now,
            get=request_json, bars_fetch=fetch_bars):
    result = {
        'hypothesis': thesis.strip()[:2000] or 'User-directed paper experiment; thesis not supplied',
        'observations': [],
        'assumptions': ['Historical momentum may not persist; a user thesis is not verified evidence'],
        'unknowns': ['Fundamental valuation, future catalysts and expected return are unverified'],
        'risks': ['Loss of the simulated position value', 'Gaps, spreads, slippage and delayed execution'],
        'falsification': 'Specify an exit rule and evaluation horizon before comparing outcomes',
        'recommendation': 'Record the experiment and evaluate future outcomes; no live-money recommendation',
        'reference': None,
    }
    if reference_price is not None:
        price = money(reference_price)
        if price <= 0:
            raise ValueError('Reference price must be positive')
        result['reference'] = {'price': str(price), 'source': 'USER_SUPPLIED_HYPOTHETICAL',
                               'observed_at_utc': None, 'is_executable_quote': False}
    if not key or not secret:
        result['unknowns'].append('Market data unavailable: paper API credentials not configured')
        return result
    try:
        data = get(DATA, '/v2/stocks/' + symbol + '/quotes/latest', key, secret,
                   params={'feed': 'iex'})
        q = data['quote']
        bid, ask = money(q['bp']), money(q['ap'])
        stamp = datetime.fromisoformat(q['t'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or stamp > now or not 0 < bid <= ask:
            raise ValueError('Invalid quote')
        age = (now-stamp).total_seconds()
        result['observations'].append({'source': 'Alpaca IEX latest quote', 'bid': str(bid),
                                       'ask': str(ask), 'timestamp': stamp.isoformat(), 'age_seconds': age})
        if result['reference'] is None:
            result['reference'] = {'price': str(ask), 'source': 'IEX_REFERENCE_ASK',
                                   'observed_at_utc': stamp.isoformat(), 'age_seconds': age,
                                   'is_executable_quote': False}
        if age > 120:
            result['unknowns'].append('Quote is older than 120 seconds; reference simulation is not a current-price fill')
    except (RuntimeError, ValueError, KeyError, TypeError, OSError):
        result['unknowns'].append('Valid latest IEX quote unavailable')
    try:
        bars = bars_fetch((symbol,), key, secret, now=now)
        report = build_report((symbol,), bars, generated_at=now.isoformat())
        result['observations'].extend(report['candidates'])
        if not report['candidates']:
            result['unknowns'].append('Insufficient historical bars for trend analysis')
    except (RuntimeError, ValueError, TypeError, KeyError):
        result['unknowns'].append('Historical trend analysis unavailable')
    return result


def submit(symbol, amount, request_id, *, key, secret, get=request_json):
    if not key or not secret:
        raise ValueError('Paper credentials missing')
    # Look up the stable ID before checking funds: a previous fill may have used cash.
    try:
        existing = get(PAPER, '/v2/orders:by_client_order_id', key, secret,
                       params={'client_order_id': request_id})
    except RuntimeError as exc:
        if str(exc) != 'Alpaca HTTP 404':
            raise
    else:
        return acknowledgment(existing, symbol, amount, request_id, existing=True)
    account = get(PAPER, '/v2/account', key, secret)
    if (account.get('status') != 'ACTIVE' or account.get('trading_blocked') is not False
            or account.get('account_blocked') is not False):
        raise ValueError('Paper account is not active and unblocked')
    if min(money(account.get('cash')), money(account.get('buying_power'))) < amount:
        raise ValueError('Insufficient paper cash or buying power')
    asset = get(PAPER, '/v2/assets/' + symbol, key, secret)
    if (asset.get('status') != 'active' or asset.get('tradable') is not True
            or asset.get('fractionable') is not True):
        raise ValueError('Asset must be active, tradable and fractionable')
    # Manual purchases deliberately do not require the automatic strategy's score,
    # news, five-position cap or market-open gate. Closed-session orders may queue.
    # POST once only. A timeout is AMBIGUOUS, never a reason to retry blindly.
    try:
        order = get(PAPER, '/v2/orders', key, secret, payload={
            'symbol': symbol, 'notional': f'{amount:.2f}', 'side': 'buy',
            'type': 'market', 'time_in_force': 'day', 'client_order_id': request_id})
    except RuntimeError:
        # A failed POST may already have reached the broker. Read-only lookup
        # may confirm an existing order; NEVER repeat the POST.
        try:
            recovered = get(PAPER, '/v2/orders:by_client_order_id', key, secret,
                            params={'client_order_id': request_id})
        except (RuntimeError, OSError):
            raise RuntimeError(
                'Order outcome uncertain; reconcile by client order ID before any new action'
            ) from None
        return acknowledgment(recovered, symbol, amount, request_id, existing=True)
    return acknowledgment(order, symbol, amount, request_id)


def acknowledgment(order, symbol, amount, request_id, *, existing=False):
    if (not isinstance(order, dict) or not order.get('id')
            or order.get('symbol') != symbol or order.get('side') != 'buy'
            or order.get('client_order_id') != request_id
            or money(order.get('notional')) != amount):
        raise RuntimeError('Ambiguous broker acknowledgment')
    status = order.get('status')
    if status not in {'new', 'accepted', 'pending_new', 'partially_filled', 'held',
                      'accepted_for_bidding', 'pending_cancel', 'pending_replace',
                      'done_for_day', 'filled', 'calculated', 'stopped', 'suspended',
                      'replaced', 'rejected', 'canceled', 'expired'}:
        raise RuntimeError('Broker status unavailable')
    rejected = status in ('rejected', 'canceled', 'expired')
    return {'status': 'BROKER_REJECTED_OR_TERMINATED' if rejected else
                     'BROKER_FILLED' if status == 'filled' else 'BROKER_ACCEPTED_PENDING_FILL',
            'broker_order_id': order['id'], 'broker_status': status,
            'order_submitted': True, 'order_filled': status == 'filled',
            'reconciled_existing_order': existing,
            'fill': {field: order.get(field) for field in ('filled_qty', 'filled_avg_price', 'filled_at')}}


def write_report(out, report):
    out.mkdir(parents=True, exist_ok=True)
    temporary = out / 'decision.json.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(out / 'decision.json')
    analysis = report['analysis']
    # User thesis and upstream text stay in JSON, not rendered as public Markdown.
    lines = ['# Paper purchase decision', '', f"Symbol: {report['symbol']}",
             f"Requested amount: ${report['notional_usd']}",
             f"Decision ID: {report['request_id']}", f"Status: {report['status']}",
             f"Broker submitted: {report['order_submitted']}",
             f"Broker filled: {report['order_filled']}", '',
             'Decision recorded and analyzed independently of broker execution.',
             'See decision.json for observations, hypothesis, assumptions, risks and unknowns.',
             'Reference-price simulations are hypothetical and are not Alpaca fills.',
             'Closed-market orders may queue. No broker fill or immediate execution is guaranteed.',
             'This command can only submit to the Alpaca PAPER endpoint.']
    if report.get('error'):
        lines.extend(['', 'Broker submission unavailable; inspect decision.json and reconcile in Alpaca.'])
    (out/'decision.md').write_text('\n'.join(lines)+'\n')


def reserve_local_submission(out, request_id):
    """Reserve one local attempt atomically; never remove on timeout.

    This does not coordinate separate ephemeral GitHub runners.
    """
    out.mkdir(parents=True, exist_ok=True)
    marker = out / 'submission-attempt.json'
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError('Submission already reserved; reconcile only') from None
    with os.fdopen(fd, 'w') as stream:
        json.dump({'request_id': request_id, 'state': 'ATTEMPT_RESERVED'}, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--notional', required=True)
    parser.add_argument('--request-id', required=True)
    parser.add_argument('--thesis', default='')
    parser.add_argument('--reference-price', default=None)
    parser.add_argument('--submit-paper', action='store_true')
    parser.add_argument('--reconcile-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=Path('paper-purchase-output'))
    args = parser.parse_args(argv)
    try:
        amount = validate(args.symbol, args.notional, args.request_id)
        # Invalid reference marks must fail before any submission.
        if args.reference_price is not None and money(args.reference_price) <= 0:
            raise ValueError('Reference price must be positive')
    except ValueError as exc:
        parser.error(str(exc))
    key, secret = os.getenv('ALPACA_API_KEY', ''), os.getenv('ALPACA_API_SECRET', '')
    now = datetime.now(timezone.utc)
    report = {'schema_version': '1.0', 'mode': 'PAPER_ONLY', 'created_at_utc': now.isoformat(),
              'request_id': args.request_id, 'symbol': args.symbol, 'notional_usd': str(amount),
              'status': 'DECISION_RECORDED', 'order_submitted': False, 'order_filled': False,
              'analysis': analyze(args.symbol, thesis=args.thesis, reference_price=args.reference_price,
                                 key=key, secret=secret, now=now)}
    reference = report['analysis']['reference']
    if reference:
        report['hypothetical_purchase'] = {
            'price': reference['price'], 'quantity': str(amount / money(reference['price'])),
            'source': reference['source'], 'broker_fill': False,
            'assumption': 'Full immediate hypothetical allocation at reference mark; excludes fees/slippage'}
        report['status'] = 'REFERENCE_SIMULATION_RECORDED'
    # Prevent local replay before any broker POST; retain marker on ambiguity.
    if args.submit_paper:
        try:
            reserve_local_submission(args.output_dir, args.request_id)
        except (RuntimeError, OSError) as exc:
            print(f'Paper submission blocked: {exc}')
            return 1
    # Preserve the intent and analysis BEFORE touching the broker, including POST timeouts.
    write_report(args.output_dir, report)
    code = 0
    if args.submit_paper or args.reconcile_only:
        try:
            if args.reconcile_only:
                if not key or not secret:
                    raise ValueError('Paper credentials missing')
                order = request_json(PAPER, '/v2/orders:by_client_order_id', key, secret,
                                     params={'client_order_id': args.request_id})
                report.update(acknowledgment(order, args.symbol, amount, args.request_id, existing=True))
            else:
                # No paper broker POST without durable cross-run coordination.
                database_url = os.getenv('PAPER_LEDGER_DATABASE_URL', '')
                if not database_url:
                    raise RuntimeError('PostgreSQL paper ledger is required for broker submission')
                import psycopg
                from postgres_paper_ledger import PostgresPaperLedger, submit_with_ledger
                with psycopg.connect(database_url, connect_timeout=10,
                                     sslmode='require', autocommit=False) as conn:
                    report.update(submit_with_ledger(
                        PostgresPaperLedger(conn), args.symbol, amount, args.request_id,
                        key=key, secret=secret, get=request_json))
            if report['status'] == 'BROKER_REJECTED_OR_TERMINATED':
                code = 1
        except Exception as exc:
            # Database/driver failures also fail closed; never retry broker POST.
            report['status'] = ('BROKER_NOT_CONFIGURED' if not key or not secret
                                else 'BROKER_UNCONFIRMED_REQUIRES_RECONCILIATION')
            report['order_submitted'] = False if not key or not secret else None  # Unknown on a timeout; never imply zero orders.
            report['error'] = type(exc).__name__
            report['next_action'] = ('Configure dedicated paper credentials, then submit this decision'
                                     if not key or not secret else
                                     'Use --reconcile-only with this same request ID; do not generate a new purchase ID')
            code = 1
        write_report(args.output_dir, report)
    print(f"Paper decision: {report['status']}; evidence: {args.output_dir}/decision.json")
    return code


if __name__ == '__main__':
    raise SystemExit(main())
