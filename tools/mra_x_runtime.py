"""MRA-X-TGA-2.0 persistent advisory research ledger and synthetic benchmark.
Local SQLite only; no external execution, proof promotion or authentication.
Use a trusted private directory; the database is not tamper-proof.
"""
import argparse
import copy
import hashlib
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

from mra_x_tga import evaluate, example, digest


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def submit(db_path, record):
    """Serialize exact claim enrollment; only candidate claims enter history.

    The caller's history is ignored in favor of ledger history. No budgets are
    actually spent or reserved by this advisory transaction. Keep DB private.
    """
    if not isinstance(record, dict):
        return evaluate(record)
    item = copy.deepcopy(record)
    claim = item.get('claim')
    key = digest(claim) if isinstance(claim, str) and claim.strip() else None
    with closing(sqlite3.connect(str(db_path), timeout=10, isolation_level=None)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS claims (claim_hash TEXT PRIMARY KEY)')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, record_hash TEXT NOT NULL, claim_hash TEXT, disposition TEXT NOT NULL, previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL)')
            exists = bool(key and db.execute('SELECT 1 FROM claims WHERE claim_hash=?', (key,)).fetchone())
            item['prior_claim_hashes'] = [key] if exists else []
            result = evaluate(item)
            record_hash = digest(canonical(item))
            if result['status'] == 'REVIEW_CANDIDATE':
                db.execute('INSERT INTO claims VALUES (?)', (key,))
            last = db.execute('SELECT event_hash FROM events ORDER BY id DESC LIMIT 1').fetchone()
            previous = last[0] if last else '0' * 64
            disposition = canonical(result)
            event_hash = digest(canonical([record_hash, key, disposition, previous]))
            db.execute('INSERT INTO events(record_hash,claim_hash,disposition,previous_hash,event_hash) VALUES (?,?,?,?,?)', (record_hash, key, disposition, previous, event_hash))
            db.execute('COMMIT')
            return dict(result, record_hash=record_hash, event_hash=event_hash)
        except Exception:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()


def audit(db_path):
    """Check hash links and candidate enrollment, not source authenticity."""
    path = Path(db_path)
    if not path.is_file():
        raise ValueError('ledger does not exist')
    with closing(sqlite3.connect(str(path))) as db:
        try:
            db.execute('BEGIN')
            previous = '0' * 64
            enrolled = set()
            count = 0
            for record_hash, key, disposition, link, event_hash in db.execute('SELECT record_hash,claim_hash,disposition,previous_hash,event_hash FROM events ORDER BY id'):
                if link != previous or event_hash != digest(canonical([record_hash, key, disposition, link])):
                    raise ValueError('ledger hash mismatch')
                result = json.loads(disposition)
                if result.get('authorizes_execution') is not False or result.get('theorem_promoted') is not False:
                    raise ValueError('invalid authority boundary')
                if result['status'] == 'REVIEW_CANDIDATE':
                    if key in enrolled or not key:
                        raise ValueError('duplicate or missing enrollment')
                    enrolled.add(key)
                previous = event_hash
                count += 1
            if enrolled != {r[0] for r in db.execute('SELECT claim_hash FROM claims')}:
                raise ValueError('claim index mismatch')
            return {'events': count, 'claims': len(enrolled), 'head': previous, 'integrity': 'consistent', 'authenticated': False}
        finally:
            db.close()


def benchmark():
    """Deterministic synthetic stage-count comparison, not live research efficacy.

    Baseline always executes seven modeled stages. Gated process rejects invalid
    records at stage four and completes seven for review candidates. The gate
    itself runs in both arms; timings are illustrative local software overhead.
    """
    cases = []
    for i in range(100):
        r = example()
        r['claim'] = 'synthetic claim ' + str(i)
        if i % 2:
            r['evidence'][0]['sha256'] = '0' * 64
        cases.append(r)
    t0 = time.perf_counter()
    baseline = [evaluate(r)['status'] for r in cases]
    t1 = time.perf_counter()
    gated = [evaluate(r)['status'] for r in cases]
    t2 = time.perf_counter()
    full = len(cases) * 7
    early = sum(7 if status == 'REVIEW_CANDIDATE' else 4 for status in gated)
    return {'cases': len(cases), 'matching_dispositions': sum(a == b for a, b in zip(baseline, gated)), 'baseline_modeled_stages': full, 'gated_modeled_stages': early, 'stage_reduction_fraction': (full-early)/full, 'baseline_gate_seconds': t1-t0, 'gated_gate_seconds': t2-t1, 'scope': 'synthetic stage accounting only; no live provider calls or scientific efficacy claims'}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'ledger.sqlite'
    def test_restart(self):
        self.assertEqual(submit(self.db, example())['status'], 'REVIEW_CANDIDATE')
        self.assertEqual(submit(self.db, example())['status'], 'STOP')
        self.assertEqual(audit(self.db)['claims'], 1)
    def test_concurrency(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: submit(self.db, example())['status'], range(4)))
        self.assertEqual(results.count('REVIEW_CANDIDATE'), 1)
        self.assertEqual(results.count('STOP'), 3)
        self.assertEqual(audit(self.db)['events'], 4)
    def test_invalid_not_enrolled(self):
        r = example(); r['evidence'] = []
        self.assertEqual(submit(self.db, r)['status'], 'DECOMPOSE')
        self.assertEqual(submit(self.db, example())['status'], 'REVIEW_CANDIDATE')
    def test_tamper(self):
        submit(self.db, example())
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE events SET previous_hash='bad'")
        with self.assertRaises(ValueError):
            audit(self.db)
    def test_index_tamper(self):
        submit(self.db, example())
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM claims')
        with self.assertRaises(ValueError):
            audit(self.db)
    def test_missing_ledger(self):
        with self.assertRaises(ValueError):
            audit(self.db)
    def test_benchmark(self):
        r = benchmark()
        self.assertEqual(r['matching_dispositions'], 100)
        self.assertEqual(r['baseline_modeled_stages'], 700)
        self.assertEqual(r['gated_modeled_stages'], 550)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--self-test', action='store_true')
    group.add_argument('--benchmark', action='store_true')
    group.add_argument('--record', type=Path)
    group.add_argument('--audit', action='store_true')
    parser.add_argument('--db', type=Path)
    args = parser.parse_args()
    if args.self_test:
        return 0 if unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeTests)).wasSuccessful() else 1
    if args.benchmark:
        result = benchmark()
    else:
        if args.db is None:
            parser.error('--db is required for record or audit')
        try:
            result = audit(args.db) if args.audit else submit(args.db, json.loads(args.record.read_text(encoding='utf-8')))
        except (ValueError, OSError, sqlite3.Error) as exc:
            parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return int(args.record is not None and result['status'] != 'REVIEW_CANDIDATE')


if __name__ == '__main__':
    raise SystemExit(main())
