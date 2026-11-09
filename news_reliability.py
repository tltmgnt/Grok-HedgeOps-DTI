"""Offline reliability diagnostics for frozen news-shadow research.

Paired opportunity returns, date-clustered circular-block bootstrap and explicit
data blockers. Never authorizes orders or certifies an economic edge.
"""
import argparse
from collections import defaultdict
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
import random
from zoneinfo import ZoneInfo

from news_topology import VERSION, research_cohorts, stamp
from news_shadow_evaluation import evaluate

METHOD = 'news-reliability-v1'
COMPARISONS = ('graph_minus_keyword', 'h0_minus_graph', 'h0_minus_keyword')
LABEL = 'five_calendar_days_next_session_close'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def quantile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def circular_bootstrap(daily, *, block_days, resamples, seed):
    """Resample contiguous entry-date clusters jointly across all policy pairs.

    Each daily vector has raw-return deltas followed by trade-count deltas. Keep
    the actual date order; block length counts observed entry dates, not calendar
    days. Prefix sums avoid expanding every selected block for every replicate.
    """
    n = len(daily)
    if not n or not 1 <= block_days <= n:
        raise ValueError('Block length must fit nonempty date series')
    rng = random.Random(seed)
    doubled = daily + daily
    prefix = [[0.0] * 6]
    for row in doubled:
        prefix.append([a + b for a, b in zip(prefix[-1], row)])
    result = []
    for _ in range(resamples):
        totals, remaining = [0.0] * 6, n
        while remaining:
            start = rng.randrange(n)
            width = min(block_days, remaining)
            totals = [t + b - a for t, a, b in zip(totals, prefix[start], prefix[start + width])]
            remaining -= width
        result.append([t / n for t in totals])
    return result


def validate_protocol(protocol):
    if (protocol.get('method_version') != METHOD or protocol.get('feature_version') != VERSION
            or protocol.get('label_policy') != LABEL):
        raise ValueError('Protocol version or label policy mismatch')
    cutoff = stamp(protocol['cutoff'])
    frozen = stamp(protocol['frozen_at']) if protocol.get('frozen_at') else None
    integer_fields = {'embargo_days': (5, 365), 'min_dates': (20, 10000),
                      'resamples': (1000, 100000), 'trials_declared': (1, 1000),
                      'seed': (0, 2**32 - 1)}
    for field, (low, high) in integer_fields.items():
        value = protocol[field]
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Invalid integer protocol field: ' + field)
    blocks, costs = protocol['block_days'], protocol['cost_bps']
    if (not isinstance(blocks, list) or not blocks or len(blocks) > 10
            or any(type(b) is not int or not 2 <= b <= 100 for b in blocks)
            or len(set(blocks)) != len(blocks)):
        raise ValueError('Invalid block lengths')
    if (not isinstance(costs, list) or not costs or len(costs) > 10
            or any(type(c) not in (float, int) or not math.isfinite(c) or c < 0 for c in costs)
            or len(set(costs)) != len(costs)):
        raise ValueError('Invalid cost scenarios')
    if frozen is not None and frozen > cutoff + timedelta(days=protocol['embargo_days']):
        raise ValueError('Freeze protocol before held-out period begins')
    return cutoff, frozen


def reliability(rows, protocol, *, asof):
    """Report paired diagnostics with data completeness separate from statistics."""
    asof = stamp(asof)
    cutoff, frozen = validate_protocol(protocol)
    if frozen is not None and frozen > asof:
        raise ValueError('Protocol freeze cannot be future dated')
    if not isinstance(rows, list):
        raise ValueError('Observation registry must be an array')
    blockers = []
    if frozen is None:
        blockers.append('DRAFT_PROTOCOL_NOT_FROZEN')
    daily = defaultdict(list)
    observed, pending, missing, excluded, seen = [], 0, 0, 0, set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid observation registry row')
        entry = stamp(row['entry_at'])
        identity = (row['symbol'], entry)
        if identity in seen:
            raise ValueError('Duplicate canonical symbol/entry timestamp')
        seen.add(identity)
        if entry > asof:
            raise ValueError('Future observation in registry')
        if type(row['keyword_pass']) is not bool:
            raise ValueError('Explicit baseline flag required')
        if entry < cutoff + timedelta(days=protocol['embargo_days']):
            excluded += 1
            continue
        if not row['keyword_pass']:
            excluded += 1
            continue
        if row.get('label_policy') != LABEL:
            raise ValueError('Inconsistent outcome horizon')
        status = row.get('outcome_status')
        if status not in ('OBSERVED', 'PENDING', 'MISSING'):
            raise ValueError('Explicit outcome status required')
        if frozen is not None and stamp(row['feature_asof']) < frozen:
            raise ValueError('Held-out features predate protocol freeze')
        # Eight calendar days allows a five-day horizon plus a weekend/session gap.
        # Older incomplete rows cannot stay pending indefinitely.
        if status == 'MISSING' or (status == 'PENDING' and asof - entry >= timedelta(days=8)):
            missing += 1
            continue
        if status == 'PENDING':
            pending += 1
            continue
        exit_at, available = stamp(row['exit_at']), stamp(row['outcome_known_at'])
        if not entry + timedelta(days=5) <= exit_at <= entry + timedelta(days=8):
            raise ValueError('Outcome outside frozen five-day/session-gap window')
        if not exit_at <= available <= asof:
            raise ValueError('Outcome not available at evaluation time')
        # Reuse baseline point-in-time, snapshot, price and version validation.
        evaluate([row], cutoff=protocol['cutoff'], embargo_days=protocol['embargo_days'], cost_bps=0)
        raw = 100 * (row['exit_price'] / row['entry_price'] - 1)
        flags = research_cohorts(row['snapshot'])
        keyword, graph, h0 = 1, int(flags['graph_quality_pass']), int(flags['h0_pass'])
        trade_deltas = [graph - keyword, h0 - graph, h0 - keyword]
        vector = [d * raw for d in trade_deltas] + trade_deltas
        day = entry.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        daily[day].append(vector)
        observed.append(row)
    dates = sorted(daily)
    # Equal weight per entry date; all same-date symbols remain in the same block.
    vectors = [[sum(v[i] for v in daily[d]) / len(daily[d]) for i in range(6)] for d in dates]
    if missing:
        blockers.append('MISSING_MATURE_OUTCOMES')
    if pending:
        blockers.append('PENDING_OUTCOMES')
    if len(dates) < protocol['min_dates']:
        blockers.append('TOO_FEW_ENTRY_DATES')
    if len(dates) < 3 * max(protocol['block_days']):
        blockers.append('TOO_FEW_BLOCKS')
    family = len(COMPARISONS) * len(protocol['block_days']) * len(protocol['cost_bps']) * protocol['trials_declared']
    tail = 0.05 / (2 * family)
    # Sparse bootstrap tails are unreliable; do not hide inadequate resolution.
    if protocol['resamples'] * tail < 10:
        blockers.append('BOOTSTRAP_TAIL_RESOLUTION_TOO_LOW')
    scenarios = []
    if not blockers:
        for block in protocol['block_days']:
            draws = circular_bootstrap(vectors, block_days=block,
                                       resamples=protocol['resamples'], seed=protocol['seed'])
            means = [sum(v[i] for v in vectors) / len(vectors) for i in range(6)]
            for cost in protocol['cost_bps']:
                for i, name in enumerate(COMPARISONS):
                    samples = [v[i] - cost / 100 * v[i + 3] for v in draws]
                    lower, upper = quantile(samples, tail), quantile(samples, 1 - tail)
                    scenarios.append({'comparison': name, 'block_entry_dates': block,
                                      'round_trip_cost_bps': cost,
                                      'paired_mean_delta_pct': means[i] - cost / 100 * means[i + 3],
                                      'interval_pct': [lower, upper],
                                      'diagnostic': 'POSITIVE_INTERVAL' if lower > 0 else
                                                    'NEGATIVE_INTERVAL' if upper < 0 else 'INCONCLUSIVE'})
    return {'method_version': METHOD, 'asof': asof.isoformat(),
            'protocol_hash': fingerprint(protocol), 'registry_hash': fingerprint(rows),
            'status': 'BLOCKED' if blockers else 'EXPLORATORY_DIAGNOSTICS', 'blockers': blockers,
            'coverage': {'registry_rows': len(rows), 'observed_held_out': len(observed),
                         'entry_dates': len(dates), 'pending': pending, 'missing': missing,
                         'outside_held_out_or_baseline': excluded},
            'family_size_declared': family, 'interval_nominal_family_coverage': 0.95,
            'interval_method': 'paired circular entry-date block bootstrap; Bonferroni percentile tails',
            'scenarios': scenarios, 'edge_verdict': 'UNPROVEN', 'order_authority': False,
            'limitations': ['Protocol timestamps/hashes are declarations, not authenticated preregistration',
                           'Registry completeness and benchmark/source provenance require independent audit',
                           'Block inference assumes sufficiently stationary weakly dependent observations',
                           'Declared trials do not discover undisclosed searches or repeated peeking',
                           'Opportunity policy returns use cash=0 for skipped entries; not a capital-constrained portfolio',
                           'Positive approximate intervals are not calibrated signal confidence or execution approval']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--asof', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = reliability(json.loads(args.input.read_text()), json.loads(args.protocol.read_text()), asof=args.asof)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
