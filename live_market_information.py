"""Read-only, on-demand Alpaca market evidence; never submits orders."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

from paper_opportunity_intelligence import PAPER, request_json, fresh_quote, news_evidence


def snapshot(symbol, *, key, secret, get=request_json, clock=None):
    if not re.fullmatch(r'[A-Z]{1,5}', symbol):
        raise ValueError('Use an uppercase stock symbol of 1–5 letters')
    if not key or not secret:
        raise ValueError('Missing Alpaca credentials')
    clock = clock or (lambda: datetime.now(timezone.utc))
    result = {'symbol': symbol, 'order_authority': False, 'status': 'UNAVAILABLE'}
    market = get(PAPER, '/v2/clock', key, secret)
    if not isinstance(market, dict) or not isinstance(market.get('is_open'), bool):
        raise ValueError('Market clock unavailable')
    result['market_open'] = market['is_open']
    result['next_open'] = market.get('next_open')
    result['next_close'] = market.get('next_close')
    # Fetch headlines first so the quote is the last observation before publishing.
    result['catalyst_headlines'] = news_evidence(symbol, key, secret, now=clock(), get=get)
    try:
        result['quote'] = fresh_quote(symbol, key, secret, now=clock(), get=get)
        result['status'] = 'CURRENT' if market['is_open'] else 'MARKET_CLOSED'
    except ValueError as exc:
        result['quote'] = None
        result['reason'] = str(exc)
    result['observed_at_utc'] = clock().isoformat()
    result['limitations'] = 'REST snapshot, not streaming. Headlines are unverified source claims; freshness does not establish factual accuracy.'
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--output', type=Path, default=Path('live-market-information.json'))
    args = parser.parse_args(argv)
    try:
        result = snapshot(args.symbol, key=os.getenv('ALPACA_API_KEY', ''),
                          secret=os.getenv('ALPACA_API_SECRET', ''))
    except (RuntimeError, ValueError, TypeError):
        # Do not expose provider responses or credential-bearing exception text.
        result = {'status': 'UNAVAILABLE', 'order_authority': False,
                  'reason': 'Market evidence unavailable; check credentials, feed entitlement and provider connectivity.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Market information status: ' + result['status'])
    return 1 if result['status'] == 'UNAVAILABLE' else 0


if __name__ == '__main__':
    raise SystemExit(main())
