"""Local durable session index and UTC calendar/rolling operational reports.

Contains no broker execution path. Keep this database on a private persistent volume.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

HORIZONS = {'1s': 1, **{f'{n}m': n * 60 for n in range(10, 61, 10)}}


def utc(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('timezone required')
    return stamp.astimezone(timezone.utc)


def start_of(horizon, now):
    if horizon in HORIZONS:
        return now - timedelta(seconds=HORIZONS[horizon])
    if horizon == 'daily':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if horizon == 'monthly':
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if horizon == 'quarterly':
        return now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1,
                           hour=0, minute=0, second=0, microsecond=0)
    raise ValueError('unknown horizon')


class Ledger:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions '
                        '(run_id TEXT PRIMARY KEY, observed TEXT NOT NULL, '
                        'status TEXT NOT NULL, strategy TEXT NOT NULL)')

    def close(self):
        self.db.close()

    def ingest(self, run_id, session):
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError('run ID required')
        observed = utc(session['observed_at_utc']).isoformat()
        status, strategy = session['status'], session['strategy_version']
        if not isinstance(strategy, str) or not strategy:
            raise ValueError('strategy required')
        if status not in {'OK', 'ERROR', 'MARKET_CLOSED'}:
            raise ValueError('unknown session status')
        row = (run_id, observed, status, strategy)
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO sessions VALUES (?, ?, ?, ?)', row)
            stored = self.db.execute('SELECT * FROM sessions WHERE run_id=?', (run_id,)).fetchone()
            if stored != row:
                raise ValueError('conflicting run ID; original record preserved')

    def report(self, horizon, now):
        now = utc(now.isoformat())
        start = start_of(horizon, now)
        rows = self.db.execute('SELECT status, strategy FROM sessions WHERE observed>=? '
                               'AND observed<=?', (start.isoformat(), now.isoformat())).fetchall()
        latest = self.db.execute('SELECT MAX(observed) FROM sessions WHERE observed<=?',
                                 (now.isoformat(),)).fetchone()[0]
        return {'horizon': horizon, 'start_utc': start.isoformat(), 'end_utc': now.isoformat(),
                'sessions': len(rows), 'status_counts': {s: sum(r[0] == s for r in rows)
                    for s in ('OK', 'ERROR', 'MARKET_CLOSED')},
                'strategy_versions': sorted({r[1] for r in rows}),
                'latest_observation_age_seconds': (now - utc(latest)).total_seconds() if latest else None,
                'coverage': 'OBSERVED_ONLY' if rows else 'NO_OBSERVATIONS',
                'limitations': ['Not a streaming collector or scheduler',
                    'No expected-run manifest: missing runs and uptime remain unverified',
                    'Session status is not proof of a fill, profit, or broker availability',
                    'UTC calendar periods; partial current periods; no P/L attribution']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path('data/workflow-ledger.sqlite3'))
    parser.add_argument('--session', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--horizon', choices=[*HORIZONS, 'daily', 'monthly', 'quarterly'], default='daily')
    args = parser.parse_args()
    ledger = Ledger(args.db)
    try:
        if args.session:
            ledger.ingest(args.run_id, json.loads(args.session.read_text()))
        print(json.dumps(ledger.report(args.horizon, datetime.now(timezone.utc)), indent=2))
    finally:
        ledger.close()


if __name__ == '__main__':
    main()
