"""Synthetic fixtures only; these checks are not market-performance evidence."""
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest

from news_topology import (VERSION, build_snapshot, canonical_url, compare_snapshots,
                           h0_persistence, research_cohorts)
from news_shadow_evaluation import evaluate
from paper_opportunity_intelligence import news_evidence
from paper_research_agent import evidence_packet

ASOF = '2026-11-08T20:00:00+00:00'


def article(headline='ACME raises guidance after strong earnings', **kwargs):
    return {'headline': headline, 'symbols': ['ACME'], 'source': 'Example Wire',
            'created_at': '2026-11-08T18:00:00Z', **kwargs}


def snapshot(rows=None, **kwargs):
    return build_snapshot(rows if rows is not None else [article()],
                          symbol='ACME', asof=kwargs.get('asof', ASOF))


def test_h0_exact_known_geometry_and_empty_singleton():
    h0 = h0_persistence([{'a', 'b'}, {'a', 'b'}, {'c'}])
    assert [i['death'] for i in h0['finite_intervals']] == [0, 1]
    assert [r['count'] for r in h0['components_by_distance']] == [2, 2, 2, 2, 1]
    assert len(h0['essential_intervals']) == 1
    assert h0_persistence([])['essential_intervals'] == []
    assert h0_persistence([{'a'}])['finite_intervals'] == []


def test_permutation_invariance_and_replay_hash():
    rows = [article(), article('ACME cuts guidance after weak earnings'),
            article('ACME launches new product')]
    a, b = snapshot(rows), snapshot(list(reversed(rows)))
    assert a == b
    assert a['input_hash'] == snapshot(deepcopy(rows))['input_hash']
    json.dumps(a, allow_nan=False)


def test_syndicated_copies_are_one_family_not_independent_votes():
    a = snapshot([article(source='Publisher A'), article(source='Publisher B')])
    assert a['coverage']['families'] == 1
    assert a['coverage']['duplicate_records'] == 1
    assert a['duplicate_families'][0]['source_labels'] == ['Publisher A', 'Publisher B']
    assert a['source_independence'].startswith('UNKNOWN')
    assert research_cohorts(a)['graph_quality_pass'] is False


def test_canonical_url_dedup_and_no_url_fetching():
    a = snapshot([article(url='https://example.invalid/story?utm_source=a'),
                  article('ACME earnings article retitled', url='https://example.invalid/story#fragment')])
    assert a['coverage']['families'] == 1
    assert canonical_url('javascript:alert(1)') is None
    assert canonical_url('https://user:password@example.invalid/') is None
    assert canonical_url('https://[broken') is None


@pytest.mark.parametrize('changes', [
    {'created_at': '2026-11-08T21:00:00Z'},
    {'updated_at': '2026-11-08T21:00:00Z'},
    {'known_at': '2026-11-08T21:00:00Z'},
    {'created_at': '2026-10-01T18:00:00Z'},
    {'created_at': '2026-11-08T18:00:00'},
    {'created_at': None}, {'headline': ''}, {'headline': '!!!'},
    {'symbols': ['OTHER']}, {'symbols': None},
])
def test_unavailable_or_malformed_evidence_is_excluded(changes):
    report = snapshot([article(**changes)])
    assert report['status'] == 'INSUFFICIENT_EVIDENCE'
    assert report['coverage']['excluded'] == 1
    assert report['nodes'] == []


def test_revisions_cannot_be_replayed_before_available():
    report = snapshot([article(updated_at='2026-11-08T19:00:00Z',
                               known_at='2026-11-08T18:30:00Z')])
    assert report['coverage']['valid'] == 0


def test_novelty_is_only_within_observed_window():
    report = snapshot([article('ACME earnings revenue results outlook',
                               created_at='2026-11-06T18:00:00Z'),
                       article('ACME earnings revenue results guidance')])
    assert len(report['clusters']) == 1
    assert report['clusters'][0]['recent_24h'] is True
    assert report['clusters'][0]['window_novel'] is False


def test_possible_conflict_and_comentions_are_not_verified_relationships():
    report = snapshot([article(symbols=['ACME', 'OTHER']),
                       article('ACME cuts guidance after strong earnings')])
    assert len(report['possible_conflicts']) == 1
    assert report['co_mentioned_symbols'] == ['OTHER']
    assert research_cohorts(report)['graph_quality_pass'] is False
    assert report['order_authority'] is False
    assert report['predictive_validation'] == 'UNPROVEN'


def test_bounds_and_invalid_configuration():
    with pytest.raises(ValueError):
        snapshot([article()] * 51)
    with pytest.raises(ValueError):
        build_snapshot([], symbol='../invalid', asof=ASOF)
    with pytest.raises(ValueError):
        build_snapshot([], symbol='ACME', asof='no date')


def test_graph_change_requires_a_real_chronological_baseline():
    a = snapshot()
    assert compare_snapshots(None, a)['status'] == 'NO_BASELINE'
    with pytest.raises(ValueError):
        compare_snapshots(a, a)
    b = snapshot([article(), article('ACME launches product')], asof='2026-11-09T20:00:00Z')
    assert compare_snapshots(a, b)['new_families'] == 1


def test_shadow_uses_same_news_response_and_cannot_change_legacy_evidence():
    calls = []
    def get(*args, **kwargs):
        calls.append((args, kwargs))
        assert 'payload' not in kwargs
        return {'news': [article(), article('ACME cuts guidance after strong earnings')]}
    now = datetime.fromisoformat(ASOF)
    legacy = news_evidence('ACME', 'k', 's', now=now, get=get)
    shadow = {}
    assert news_evidence('ACME', 'k', 's', now=now, get=get, shadow=shadow) == legacy
    assert len(calls) == 2  # One request per call, no graph-specific retrieval.
    assert shadow['possible_conflicts']
    decision = {'symbol': 'ACME', 'catalyst_headlines': legacy}
    assert evidence_packet(decision) == evidence_packet({**decision, 'news_topology_shadow': shadow})


def test_shadow_invalid_batch_does_not_promote_or_change_legacy_result():
    shadow = {}
    evidence = news_evidence('ACME', 'k', 's', now=datetime.fromisoformat(ASOF),
        get=lambda *a, **k: {'news': [article()] * 51}, shadow=shadow)
    assert len(evidence) == 3
    assert shadow['status'] == 'INVALID_INPUT'
    assert shadow['order_authority'] is False


def test_assessment_records_shadow_without_changing_trade_eligibility(monkeypatch):
    import paper_opportunity_intelligence as trader
    monkeypatch.setenv('PAPER_AUTO_TRADING_ENABLED', 'true')
    monkeypatch.setenv('PAPER_AUTO_KILL_SWITCH', 'false')
    monkeypatch.setenv('PAPER_ALLOCATION_MODE', 'legacy')
    monkeypatch.setenv('PAPER_REQUIRE_FRESH_QUOTE', 'false')
    candidate = dict(symbol='ACME', score=80, return_5d_pct=7, return_20d_pct=15,
                     relative_volume_1d=2, daily_volatility_20d_pct=1.2,
                     max_drawdown_30d_pct=6, above_ma20=True,
                     last_bar_utc='2026-11-07T20:00:00Z')
    monkeypatch.setattr(trader, 'build_report', lambda *a, **k: {'candidates': [candidate]})
    rows = [article(), article('ACME cuts guidance after strong earnings')]
    def get(host, path, key, secret, *, params=None, payload=None):
        assert payload is None
        if path == '/v2/clock':
            return {'is_open': True}
        if path == '/v2/account':
            return dict(status='ACTIVE', trading_blocked=False, account_blocked=False,
                        equity='1000', last_equity='1000', cash='1000', buying_power='1000')
        if path in ('/v2/positions', '/v2/orders'):
            return []
        if path == '/v2/assets/ACME':
            return dict(status='active', tradable=True, fractionable=True)
        if path == '/v1beta1/news':
            return {'news': rows}
        raise AssertionError(path)
    decision = trader.assess(now=datetime.fromisoformat(ASOF), key='k', secret='s',
                             get=get, bars_fetch=lambda *a, **k: {})
    assert decision['decision'] == 'READY'
    assert decision['news_topology_shadow']['possible_conflicts']
    assert decision['news_topology_shadow']['order_authority'] is False


def observation(entry='2026-11-08T21:00:00Z', exit_at='2026-11-09T21:00:00Z'):
    snap = snapshot([article('ACME earnings revenue results outlook'),
                     article('ACME earnings revenue results guidance')])
    return dict(symbol='ACME', entry_at=entry, exit_at=exit_at, feature_asof=ASOF,
                known_at=ASOF, feature_version=VERSION, snapshot=snap, keyword_pass=True,
                entry_price=100, exit_price=102, benchmark_entry=100, benchmark_exit=101)


def test_evaluation_purges_overlap_applies_costs_and_does_not_certify_edge():
    rows = [observation(), observation(entry='2026-11-10T21:00:00Z', exit_at='2026-11-12T21:00:00Z')]
    result = evaluate(rows, cutoff='2026-11-11T00:00:00Z')
    assert result['purged_observations'] == 1
    baseline = result['cohorts']['development']['keyword']
    assert baseline['mean_net_return_pct'] == pytest.approx(1.9)
    assert baseline['mean_excess_return_pct'] == pytest.approx(1)
    assert result['cohorts']['held_out']['keyword']['mean_net_return_pct'] is None
    assert result['edge_verdict'] == 'UNPROVEN'


def test_evaluation_held_out_is_chronological_and_uses_recomputed_ablations():
    row = observation(entry='2026-11-16T21:00:00Z', exit_at='2026-11-17T21:00:00Z')
    # Caller cannot set h0_pass=False to silently change the versioned cohort.
    row['h0_pass'] = False
    result = evaluate([row], cutoff='2026-11-11T00:00:00Z')
    assert result['cohorts']['held_out']['graph_quality_h0']['observations'] == 1


@pytest.mark.parametrize('changes', [
    {'known_at': '2026-11-09T00:00:00Z'}, {'feature_version': 'wrong'},
    {'exit_at': '2026-11-08T20:00:00Z'}, {'entry_price': float('nan')},
    {'benchmark_exit': 0}, {'keyword_pass': 1},
])
def test_evaluation_rejects_lookahead_and_invalid_outcomes(changes):
    with pytest.raises(ValueError):
        evaluate([{**observation(), **changes}], cutoff='2026-11-11T00:00:00Z')


def test_evaluation_rejects_duplicate_observations():
    with pytest.raises(ValueError):
        evaluate([observation(), observation()], cutoff='2026-11-11T00:00:00Z')


def test_offline_replay_and_evaluation_cli(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    source, output = tmp_path / 'news.json', tmp_path / 'snapshot.json'
    source.write_text(json.dumps([article()]))
    subprocess.run([sys.executable, str(root / 'news_topology.py'), '--input', str(source),
                    '--output', str(output), '--symbol', 'ACME', '--asof', ASOF], check=True)
    replayed = json.loads(output.read_text())
    assert replayed['change']['status'] == 'NO_BASELINE'
    assert replayed['order_authority'] is False
    source.write_text(json.dumps([observation()]))
    subprocess.run([sys.executable, str(root / 'news_shadow_evaluation.py'), '--input', str(source),
                    '--output', str(output), '--cutoff', '2026-11-11T00:00:00Z'], check=True)
    assert json.loads(output.read_text())['edge_verdict'] == 'UNPROVEN'


def test_h0_counts_match_independent_graph_traversal():
    # Independently check connected components at filtration thresholds with DFS.
    from news_topology import similarity
    sets = [{'a', 'b'}, {'b', 'c'}, {'d'}, {'a', 'b', 'c'}, {'e', 'd'}]
    result = h0_persistence(sets)
    for row in result['components_by_distance']:
        unseen, count = set(range(len(sets))), 0
        while unseen:
            stack = [unseen.pop()]
            count += 1
            while stack:
                i = stack.pop()
                adjacent = {j for j in unseen if 1 - similarity(sets[i], sets[j]) <= row['distance']}
                unseen -= adjacent
                stack.extend(adjacent)
        assert row['count'] == count


def test_research_cohorts_reject_missing_versions_and_mismatched_snapshot():
    with pytest.raises(ValueError):
        research_cohorts({'version': 'future'})
    row = observation()
    row['snapshot']['symbol'] = 'OTHER'
    with pytest.raises(ValueError):
        evaluate([row], cutoff='2026-11-11T00:00:00Z')


@pytest.mark.parametrize('kwargs', [{'embargo_days': 0}, {'embargo_days': True},
                                 {'cost_bps': -1}, {'cost_bps': float('inf')}])
def test_evaluation_rejects_invalid_policy(kwargs):
    with pytest.raises(ValueError):
        evaluate([observation()], cutoff='2026-11-11T00:00:00Z', **kwargs)
