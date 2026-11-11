"""Import verified, recent OFFLINE evidence as an incomplete assurance bundle.

This import NEVER marks an assurance requirement as satisfied. The independent
assurance register must supply separately reviewed evidence for every gate.
"""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

EXPECTED = frozenset({
    'release-check.log', 'run-status.json', 'simulation.json',
    'simulation.txt', 'validation.json',
})
MAX_AGE = timedelta(minutes=95)
MAX_FILE_BYTES = 24_000
MAX_TOTAL_BYTES = 30_000
MAX_BUNDLE_BYTES = 48_000


def gh(*args):
    return subprocess.run(['gh', *args], check=True, capture_output=True,
                          text=True, timeout=60).stdout


def api(path):
    return json.loads(gh('api', path))


def iso(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def collect(repo, sha, now, output):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('invalid repository')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('invalid commit')
    data = api(f'repos/{repo}/actions/workflows/hourly-offline-release.yml/runs?branch=main&status=success&per_page=10')
    eligible = [run for run in data['workflow_runs'] if
        run.get('conclusion') == 'success' and run.get('status') == 'completed'
        and run.get('head_branch') == 'main' and run.get('head_sha') == sha
        and run.get('event') in ('schedule', 'workflow_dispatch')
        and timedelta(0) <= now - iso(run['updated_at']) <= MAX_AGE]
    if not eligible:
        raise ValueError('no fresh matching successful offline run')
    run = max(eligible, key=lambda item: iso(item['updated_at']))
    run_id = int(run['id'])
    artifacts = api(f'repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100')['artifacts']
    name = f'hourly-offline-evidence-{run_id}'
    matches = [a for a in artifacts if a.get('name') == name and not a.get('expired')
               and 0 < a.get('size_in_bytes', 0) <= 200_000]
    if len(matches) != 1:
        raise ValueError('hourly evidence artifact unavailable')
    with tempfile.TemporaryDirectory(prefix='offline-assurance-') as temp:
        root = Path(temp)
        gh('run', 'download', str(run_id), '-R', repo, '-n', name, '-D', str(root))
        entries = list(root.iterdir())
        if {p.name for p in entries} != EXPECTED or any(
                not p.is_file() or p.is_symlink() for p in entries):
            raise ValueError('missing or unexpected evidence files')
        raw = {p.name: p.read_bytes() for p in entries}
        if any(len(blob) > MAX_FILE_BYTES for blob in raw.values()) or sum(
                map(len, raw.values())) > MAX_TOTAL_BYTES:
            raise ValueError('evidence exceeds size limit')
        status = json.loads(raw['run-status.json'])
        validation = json.loads(raw['validation.json'])
        if (status.get('status') != 'PASS'
                or status.get('checks') != {
                    'RELEASE_OUTCOME': 'success', 'SIMULATION_OUTCOME': 'success',
                    'VALIDATION_OUTCOME': 'success'}
                or status.get('mode') != 'OFFLINE_SYNTHETIC_ONLY'
                or type(status.get('broker_orders_submitted')) is not int
                or status['broker_orders_submitted'] != 0
                or status.get('live_integrations_verified') is not False
                or validation.get('status') != 'PASS'
                or validation.get('mode') != 'OFFLINE_SYNTHETIC_ONLY'
                or type(validation.get('broker_orders_submitted')) is not int
                or validation['broker_orders_submitted'] != 0):
            raise ValueError('offline run validation not established')
        # This is an import record, NOT an assurance attestation. No requirement
        # entries are generated and the three evidence gates remain incomplete.
        from assurance_register import template
        register = template()
        register['strategy_version'] = 'UNATTESTED_SOURCE_' + sha[:12]
        bundle = {'register': register, 'artifacts': {
            'offline/' + name: base64.b64encode(raw[name]).decode('ascii')
            for name in sorted(raw)}}
        serialized = json.dumps(bundle, separators=(',', ':'))
        if len(serialized.encode()) > MAX_BUNDLE_BYTES:
            raise ValueError('bundle exceeds assurance limit')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding='utf-8')
        output.chmod(0o600)
    return run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        collect(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_SHA'],
                datetime.now(timezone.utc), args.output)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError,
            json.JSONDecodeError):
        print('::error::No verified recent offline artifact available; assurance remains blocked.')
        return 1
    print('Imported recent offline artifact as incomplete assurance input; no requirements approved.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
