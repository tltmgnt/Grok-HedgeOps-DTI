"""Offline, chronological shadow-cohort comparison. No broker or network access.

Accept an archived point-in-time research dataset, not a retrospectively selected
list of winning trades. Summary statistics are descriptive, never an edge verdict.
"""
import argparse
from datetime import timedelta
import json
import math
from pathlib import Path

from news_topology import VERSION, stamp, research_cohorts


def evaluate(rows, *, cutoff, embargo_days=5, cost_bps=10):
    """Compare fixed keyword / graph-quality / H0 cohorts on matched observations.

    Rows require entry/exit prices for stock and benchmark, archived signals and
    known-at timestamps. Entire overlapping label intervals are purged at cutoff.
    The same entry and exit dates and round-trip cost assumption apply to all.
    """
    cutoff = stamp(cutoff)
    if (not isinstance(rows, list) or not isinstance(embargo_days, int)
            or isinstance(embargo_days, bool) or embargo_days < 5
            or isinstance(cost_bps, bool) or not isinstance(cost_bps, (float, int))
            or not math.isfinite(cost_bps) or cost_bps < 0):
        raise ValueError('Invalid dataset or evaluation policy')
    groups = {split: {name: [] for name in ('keyword', 'graph_quality', 'graph_quality_h0')}
              for split in ('development', 'held_out')}
    seen, purged = set(), 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid observation')
        identity = (row['symbol'], row['entry_at'])
        if identity in seen:
            raise ValueError('Duplicate symbol/entry observation')
        seen.add(identity)
        entry, exit_at, feature_asof = map(stamp, (row['entry_at'], row['exit_at'], row['feature_asof']))
        if not stamp(row['known_at']) <= feature_asof <= entry < exit_at:
            raise ValueError('Feature availability or outcome chronology invalid')
        if row['feature_version'] != VERSION:
            raise ValueError('Feature version mismatch')
        if type(row['keyword_pass']) is not bool:
            raise ValueError('Explicit baseline flag required')
        snapshot = row['snapshot']
        if (stamp(snapshot['asof']) != feature_asof or snapshot['symbol'] != row['symbol']
                or any(stamp(n['known_at']) > feature_asof for n in snapshot['nodes'])):
            raise ValueError('Snapshot does not match point-in-time observation')
        flags = research_cohorts(snapshot)
        prices = [row[k] for k in ('entry_price', 'exit_price', 'benchmark_entry', 'benchmark_exit')]
        if any(isinstance(p, bool) or not isinstance(p, (float, int)) or not math.isfinite(p) or p <= 0 for p in prices):
            raise ValueError('Positive finite prices required')
        if exit_at < cutoff:
            split = 'development'
        elif entry >= cutoff + timedelta(days=embargo_days):
            split = 'held_out'
        else:
            purged += 1
            continue
        stock = 100 * (prices[1] / prices[0] - 1) - cost_bps / 100
        benchmark = 100 * (prices[3] / prices[2] - 1) - cost_bps / 100
        values = {'net_return_pct': stock, 'benchmark_net_return_pct': benchmark,
                  'excess_return_pct': stock - benchmark}
        if row['keyword_pass']:
            groups[split]['keyword'].append(values)
            if flags['graph_quality_pass']:
                groups[split]['graph_quality'].append(values)
                if flags['h0_pass']:
                    groups[split]['graph_quality_h0'].append(values)
    summaries = {}
    for split, cohorts in groups.items():
        summaries[split] = {}
        for name, values in cohorts.items():
            summaries[split][name] = {'observations': len(values), **{
                'mean_' + key: sum(v[key] for v in values) / len(values) if values else None
                for key in ('net_return_pct', 'benchmark_net_return_pct', 'excess_return_pct')}}
    return {'feature_version': VERSION, 'cutoff': cutoff.isoformat(),
            'embargo_calendar_days': embargo_days, 'round_trip_cost_bps': cost_bps,
            'purged_observations': purged, 'cohorts': summaries,
            'edge_verdict': 'UNPROVEN',
            'limitations': ['Cohort flags and thresholds must be frozen before held-out observation',
                           'Caller must supply all eligible observations, delistings and point-in-time provenance',
                           'Means are not a portfolio backtest; overlapping returns are dependent',
                           'No significance, cash-flow accounting, market impact or live-fill claim']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cutoff', required=True)
    parser.add_argument('--cost-bps', type=float, default=10)
    args = parser.parse_args()
    result = evaluate(json.loads(args.input.read_text()), cutoff=args.cutoff, cost_bps=args.cost_bps)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
