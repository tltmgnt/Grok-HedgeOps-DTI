"""Bounded, deterministic news graph research. Never grants trading authority.

H0 persistence describes lexical headline connectivity, not truth, sentiment,
causality, supplier relationships or expected returns. No network dependencies.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

VERSION = 'news-topology-shadow-v1'
MAX_ARTICLES = 50
STOP = {'the', 'a', 'an', 'of', 'to', 'and', 'in', 'on', 'for', 'as', 'at', 'by', 'with'}
TOPICS = {
    'guidance': {'guidance', 'outlook'},
    'earnings': {'earnings', 'revenue', 'results'},
    'regulatory': {'approval', 'approved', 'rejected', 'rejection'},
    'commercial': {'contract', 'partnership', 'launch'},
    'analyst': {'upgrade', 'downgrade'},
}
POSITIVE = {'raises', 'raised', 'beats', 'beat', 'approved', 'upgrade'}
NEGATIVE = {'cuts', 'cut', 'misses', 'missed', 'rejected', 'downgrade'}


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone-aware timestamp required')
    return result.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def tokens(headline):
    return set(re.findall(r'[a-z0-9]+', headline.lower())) - STOP


def similarity(left, right):
    return len(left & right) / len(left | right) if left | right else 0.0


def canonical_url(value):
    """Remove tracking/query fragments; never fetch publisher URLs."""
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
            return None
        return urlunsplit((url.scheme.lower(), url.hostname.lower(), url.path.rstrip('/'), '', ''))
    except ValueError:
        return None


def h0_persistence(token_sets):
    """Exact H0 of the complete Jaccard-distance filtration (single-linkage MST).

    Vertices are born at distance 0; an edge merges components at its distance.
    One essential interval survives, represented by death=None. No H1 is computed.
    """
    parent = list(range(len(token_sets)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = sorted((1 - similarity(a, b), i, j)
                   for i, a in enumerate(token_sets) for j, b in enumerate(token_sets) if i < j)
    deaths = []
    for distance, i, j in edges:
        a, b = find(i), find(j)
        if a != b:
            parent[b] = a
            deaths.append(round(distance, 8))
    return {'finite_intervals': [{'birth': 0, 'death': d} for d in deaths],
            'essential_intervals': [{'birth': 0, 'death': None}] if token_sets else [],
            'components_by_distance': [
                {'distance': d, 'count': len(token_sets) - sum(x <= d for x in deaths)}
                for d in (0, 0.25, 0.5, 0.75, 1)],
            'scope': 'H0 of lexical Jaccard filtration; no higher homology or truth inference'}


def build_snapshot(articles, *, symbol, asof):
    """Analyze the supplied point-in-time batch; timestamps after asof are excluded.

    Live ingestion defaults known_at to this snapshot time. Historical replay must
    supply archived known_at (first availability), not retrospective publication time.
    Reports are bounded to the existing provider request limit, never full-market.
    """
    asof = stamp(asof)
    if not isinstance(articles, list) or len(articles) > MAX_ARTICLES:
        raise ValueError('Expected at most 50 news records')
    if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z]{1,5}', symbol):
        raise ValueError('Invalid symbol')
    valid, excluded = [], 0
    for article in articles:
        try:
            if not isinstance(article, dict):
                raise ValueError('Invalid record')
            headline, symbols = article.get('headline'), article.get('symbols')
            if (not isinstance(headline, str) or not 1 <= len(headline) <= 2000
                    or not isinstance(symbols, list) or len(symbols) > 100 or symbol not in symbols):
                raise ValueError('Invalid headline or symbols')
            published = stamp(article.get('created_at'))
            updated = stamp(article.get('updated_at', article.get('created_at')))
            known = stamp(article.get('known_at', asof.isoformat()))
            if not asof - timedelta(days=7) <= published <= updated <= known <= asof:
                raise ValueError('Unavailable, future, or stale evidence')
            words = tokens(headline)
            if not words:
                raise ValueError('Empty token set')
            url = canonical_url(article.get('url'))
            source = article.get('source')
            source = source.strip()[:120] if isinstance(source, str) and source.strip() else None
            mentions = sorted({s for s in symbols if isinstance(s, str) and re.fullmatch(r'[A-Z]{1,5}', s)})
            identity = digest([headline, published.isoformat(), updated.isoformat(), url, source, mentions])
            valid.append({'id': identity, 'headline': headline, 'tokens': words,
                          'published_at': published.isoformat(), 'updated_at': updated.isoformat(),
                          'known_at': known.isoformat(), 'url': url, 'source': source,
                          'symbols': mentions})
        except (ValueError, TypeError, OverflowError):
            excluded += 1
    valid.sort(key=lambda a: (a['published_at'], a['id']))
    # Conservative lexical/canonical-URL families. Sources in a family never count
    # as independent corroboration. This cannot detect every syndicated paraphrase.
    families = []
    for item in valid:
        family = next((f for f in families if any(
            (item['url'] is not None and item['url'] == m['url'])
            or similarity(item['tokens'], m['tokens']) >= 0.9 for m in f)), None)
        if family is None:
            families.append([item])
        else:
            family.append(item)
    representatives = [f[0] for f in families]
    adjacency = {i: set() for i in range(len(families))}
    edges = []
    for i, left in enumerate(representatives):
        for j in range(i + 1, len(representatives)):
            sim = similarity(left['tokens'], representatives[j]['tokens'])
            if sim >= 0.5:
                adjacency[i].add(j)
                adjacency[j].add(i)
                edges.append({'left': left['id'], 'right': representatives[j]['id'],
                              'similarity': round(sim, 8), 'relation': 'lexical_similarity'})
    clusters, seen = [], set()
    for start in adjacency:
        if start in seen:
            continue
        pending, members = [start], set()
        while pending:
            node = pending.pop()
            if node in members:
                continue
            members.add(node)
            pending.extend(adjacency[node] - members)
        seen |= members
        rows = [representatives[i] for i in sorted(members)]
        recent = [r for r in rows if stamp(r['published_at']) > asof - timedelta(days=1)]
        # Window novelty, not a claim that the real event never appeared elsewhere.
        clusters.append({'members': [r['id'] for r in rows],
                         'recent_24h': bool(recent),
                         'window_novel': bool(recent) and len(recent) == len(rows)})
    conflict_pairs = []
    for i, a in enumerate(representatives):
        for b in representatives[i + 1:]:
            topics = sorted(t for t, vocabulary in TOPICS.items()
                            if a['tokens'] & vocabulary and b['tokens'] & vocabulary)
            opposite = ((a['tokens'] & POSITIVE and b['tokens'] & NEGATIVE)
                        or (b['tokens'] & POSITIVE and a['tokens'] & NEGATIVE))
            if topics and opposite and abs(stamp(a['published_at']) - stamp(b['published_at'])) <= timedelta(days=1):
                conflict_pairs.append({'left': a['id'], 'right': b['id'], 'topics': topics})
    nodes = [{k: v for k, v in r.items() if k != 'tokens'} for r in representatives]
    return {'version': VERSION, 'mode': 'SHADOW_ONLY', 'order_authority': False,
            'symbol': symbol, 'asof': asof.isoformat(),
            'input_hash': digest([{k: sorted(v) if k == 'tokens' else v for k, v in r.items()} for r in valid]),
            'coverage': {'received': len(articles), 'valid': len(valid), 'excluded': excluded,
                         'families': len(families), 'duplicate_records': len(valid) - len(families),
                         'scope': 'One symbol; provider top-50 seven-day batch; possibly truncated'},
            'status': 'OBSERVED' if valid else 'INSUFFICIENT_EVIDENCE',
            'nodes': nodes, 'edges': edges, 'clusters': clusters,
            'duplicate_families': [{'representative': f[0]['id'], 'members': sorted({r['id'] for r in f}),
                                    'source_labels': sorted({r['source'] for r in f if r['source']})} for f in families],
            'co_mentioned_symbols': sorted({s for r in valid for s in r['symbols'] if s != symbol}),
            'possible_conflicts': conflict_pairs,
            'h0': h0_persistence([r['tokens'] for r in representatives]),
            'source_independence': 'UNKNOWN; publisher labels and URLs do not prove independence',
            'predictive_validation': 'UNPROVEN',
            'limitations': ['Lexical clusters are not verified events',
                           'Opposing words are review flags, not factual contradictions or sentiment',
                           'Co-mentions are not verified commercial relationships or causal spillovers',
                           'Window novelty is not historical novelty',
                           'No trading score, recommendation, or automatic policy change']}


def compare_snapshots(previous, current):
    """Describe observed graph change; absence of a prior snapshot stays unknown."""
    if previous is None:
        return {'status': 'NO_BASELINE', 'new_families': None, 'disappeared_families': None}
    if (previous['version'] != current['version'] or previous['symbol'] != current['symbol']
            or stamp(previous['asof']) >= stamp(current['asof'])):
        raise ValueError('Comparable chronological snapshots required')
    before = {n['id'] for n in previous['nodes']}
    after = {n['id'] for n in current['nodes']}
    return {'status': 'OBSERVED', 'new_families': len(after - before),
            'disappeared_families': len(before - after),
            'scope': 'Batch and rolling-window changes can reflect provider coverage, not market regime'}


def research_cohorts(snapshot):
    """Frozen exploratory ablations, not calibrated quality or trade eligibility.

    Graph cohort: complete accepted batch, >=2 headline families, a recent window-
    novel cluster, no opposing-word flag. H0 cohort adds a merge by distance 0.5.
    These arbitrary versioned settings must not be tuned on held-out outcomes.
    """
    if snapshot.get('version') != VERSION or snapshot.get('mode') != 'SHADOW_ONLY':
        raise ValueError('Unsupported snapshot')
    graph = (snapshot['status'] == 'OBSERVED' and snapshot['coverage']['excluded'] == 0
             and snapshot['coverage']['families'] >= 2
             and any(c['window_novel'] for c in snapshot['clusters'])
             and not snapshot['possible_conflicts'])
    h0 = graph and any(i['death'] <= 0.5 for i in snapshot['h0']['finite_intervals'])
    return {'graph_quality_pass': graph, 'h0_pass': h0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--asof', required=True)
    parser.add_argument('--previous', type=Path)
    args = parser.parse_args()
    result = build_snapshot(json.loads(args.input.read_text()), symbol=args.symbol, asof=args.asof)
    previous = json.loads(args.previous.read_text()) if args.previous else None
    result['change'] = compare_snapshots(previous, result)
    result['research_cohorts'] = research_cohorts(result)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
