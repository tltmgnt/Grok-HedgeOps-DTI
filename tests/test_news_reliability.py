"""Synthetic inference invariants; not empirical evidence for stock prediction."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from news_reliability import (LABEL, METHOD, circular_bootstrap, fingerprint,
                              quantile, reliability)
from news_topology import VERSION, build_snapshot
from news_shadow_evaluation import evaluate


def protocol(**changes):
    return dict(method_version=METHOD, feature_version=VERSION,
                label_policy=LABEL, frozen_at='2026-01-01T00:00:00Z',
                cutoff='2026-01-02T00:00:00Z', embargo_days=5,
                min_dates=20, block_days=[5], cost_bps=[10],
                resamples=2000, trials_declared=1, seed=12, **changes)


def observation(index=0, *, symbol='ACME', h0=True, gain=0.0, status='OBSERVED'):
    entry = datetime(2026, 1, 10, 21, tzinfo=timezone.utc) + timedelta(days=index)
    feature = entry - timedelta(hours=1)
    headlines = (['ACME earnings revenue results outlook', 'ACME earnings revenue results guidance']
                 if h0 else ['ACME earnings revenue outlook', 'ACME launches product partnership'])
    articles = [dict(headline=h.replace('ACME', symbol), symbols=[symbol], source='Synthetic',
                     created_at=feature.isoformat(), known_at=feature.isoformat()) for h in headlines]
    snapshot = build_snapshot(articles, symbol=symbol, asof=feature.isoformat())
    exit_at = entry + timedelta(days=5)
    return dict(symbol=symbol, entry_at=entry.isoformat(), exit_at=exit_at.isoformat(),
                known_at=feature.isoformat(), feature_asof=feature.isoformat(),
                feature_version=VERSION, snapshot=snapshot, keyword_pass=True,
                label_policy=LABEL, outcome_status=status, outcome_known_at=exit_at.isoformat(),
                entry_price=100, exit_price=100 + gain, benchmark_entry=100, benchmark_exit=100)


ASOF = '2026-06-01T00:00:00Z'


def test_no_data_or_unfrozen_protocol_never_produces_evidence():
    p = protocol()
    p['frozen_at'] = None
    report = reliability([], p, asof=ASOF)
    assert 'DRAFT_PROTOCOL_NOT_FROZEN' in report['blockers']
    assert 'TOO_FEW_ENTRY_DATES' in report['blockers']
    assert report['scenarios'] == []
    assert report['edge_verdict'] == 'UNPROVEN'
    assert report['order_authority'] is False


def test_all_zero_null_cannot_become_positive_evidence():
    report = reliability([observation(i) for i in range(20)], protocol(), asof=ASOF)
    assert report['status'] == 'EXPLORATORY_DIAGNOSTICS'
    assert all(s['diagnostic'] == 'INCONCLUSIVE' for s in report['scenarios'])
    assert all(s['interval_pct'] == [0, 0] for s in report['scenarios'])


def test_h0_filter_is_compared_against_graph_on_same_opportunities_with_cash_for_skips():
    # H0 rejects losing observations. Reproducible synthetic direction, not market alpha.
    rows = [observation(i, h0=i % 2 == 0, gain=1 if i % 2 == 0 else -2) for i in range(20)]
    report = reliability(rows, protocol(), asof=ASOF)
    primary = next(s for s in report['scenarios'] if s['comparison'] == 'h0_minus_graph')
    assert primary['paired_mean_delta_pct'] == pytest.approx(1.05)
    assert primary['interval_pct'][0] > 0
    assert report['edge_verdict'] == 'UNPROVEN'
    shuffled = reliability(list(reversed(rows)), protocol(), asof=ASOF)
    assert report['scenarios'] == shuffled['scenarios']
    assert report['registry_hash'] != shuffled['registry_hash']  # Exact archive bytes/order are auditable.


def test_date_clustering_does_not_inflate_sample_size_with_same_day_symbols():
    one = [observation(i, h0=i % 2 == 0, gain=-1) for i in range(20)]
    two = one + [observation(i, symbol='OTHER', h0=i % 2 == 0, gain=-1) for i in range(20)]
    a, b = reliability(one, protocol(), asof=ASOF), reliability(two, protocol(), asof=ASOF)
    assert a['coverage']['entry_dates'] == b['coverage']['entry_dates'] == 20
    assert a['scenarios'] == b['scenarios']


def test_pending_and_missing_labels_are_visible_and_block_inference():
    row = observation(status='PENDING')
    early = '2026-01-11T00:00:00Z'
    report = reliability([row], protocol(), asof=early)
    assert report['coverage']['pending'] == 1
    assert 'PENDING_OUTCOMES' in report['blockers']
    later = reliability([row], protocol(), asof=ASOF)
    assert later['coverage']['missing'] == 1
    assert 'MISSING_MATURE_OUTCOMES' in later['blockers']
    assert later['scenarios'] == []


def test_duplicate_timezone_spellings_are_rejected_by_both_evaluators():
    row, alternate = observation(), observation()
    alternate['entry_at'] = alternate['entry_at'].replace('+00:00', 'Z')
    with pytest.raises(ValueError, match='Duplicate'):
        reliability([row, alternate], protocol(), asof=ASOF)
    with pytest.raises(ValueError, match='Duplicate'):
        evaluate([row, alternate], cutoff=protocol()['cutoff'])


@pytest.mark.parametrize('changes', [
    {'outcome_known_at': '2027-01-01T00:00:00Z'},
    {'outcome_known_at': '2026-01-10T21:00:00Z'},
    {'exit_at': '2026-01-12T21:00:00Z'},
    {'exit_at': '2026-02-10T21:00:00Z'},
    {'feature_asof': '2025-01-01T00:00:00Z'},
    {'entry_price': True}, {'outcome_status': 'FILLED'},
    {'label_policy': 'pick_best_return'},
])
def test_invalid_labels_or_lookahead_fail_closed(changes):
    with pytest.raises(ValueError):
        reliability([{**observation(), **changes}], protocol(), asof=ASOF)


@pytest.mark.parametrize('field,value', [
    ('resamples', True), ('min_dates', 1), ('trials_declared', 0),
    ('block_days', [0]), ('block_days', [5, 5]), ('cost_bps', [float('nan')]),
    ('cost_bps', [-1]), ('embargo_days', 0), ('seed', -1),
    ('method_version', 'wrong'), ('frozen_at', '2027-01-01T00:00:00Z'),
])
def test_invalid_protocol_is_rejected(field, value):
    p = protocol()
    p[field] = value
    with pytest.raises(ValueError):
        reliability([], p, asof=ASOF)


def test_declared_searches_reduce_tail_resolution_instead_of_granting_pass():
    p = protocol()
    p['trials_declared'] = 10
    report = reliability([observation(i) for i in range(20)], p, asof=ASOF)
    assert 'BOOTSTRAP_TAIL_RESOLUTION_TOO_LOW' in report['blockers']
    assert report['family_size_declared'] == 30


def test_circular_blocks_preserve_paired_joint_relationship_and_are_seeded():
    daily = [[float(i), float(i) * 2, 0, 0, 0, 0] for i in range(20)]
    a = circular_bootstrap(daily, block_days=5, resamples=50, seed=1)
    assert a == circular_bootstrap(daily, block_days=5, resamples=50, seed=1)
    assert all(v[1] == pytest.approx(2 * v[0]) for v in a)
    assert a != circular_bootstrap(daily, block_days=5, resamples=50, seed=2)
    assert quantile([0, 10], .25) == 2.5


def test_cli_reports_real_blockers_on_empty_registry(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    source, policy, output = (tmp_path / n for n in ('rows.json', 'protocol.json', 'report.json'))
    source.write_text('[]')
    policy.write_text(json.dumps(protocol()))
    subprocess.run([sys.executable, str(root / 'news_reliability.py'), '--input', str(source),
                    '--protocol', str(policy), '--asof', ASOF, '--output', str(output)], check=True)
    report = json.loads(output.read_text())
    assert report['status'] == 'BLOCKED'
    assert report['protocol_hash'] == fingerprint(protocol())
