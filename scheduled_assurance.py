"""Scheduled private evidence checks with deliberately redacted public summaries."""
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from assurance_register import assess

CADENCES = {'3,13,23,33,43,53 * * * *': 'ten-minute',
            '13 23 * * *': 'daily', '23 0 1 * *': 'monthly',
            '43 0 1 1,4,7,10 *': 'quarterly'}
MAX_BYTES = 48000


def check_bundle(raw, cadence, now):
    """Never return caller-supplied text, file contents, IDs or exception details."""
    report = {'cadence': cadence, 'status': 'INVALID_EVIDENCE',
              'execution_authorized': False, 'certification_issued': False}
    if not raw:
        return {**report, 'status': 'NOT_CONFIGURED'}, 1
    try:
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError('bundle too large')
        bundle = json.loads(raw)
        artifacts = bundle['artifacts']
        if not isinstance(artifacts, dict) or len(artifacts) > 100:
            raise ValueError('invalid artifacts')
        with tempfile.TemporaryDirectory(prefix='assurance-') as directory:
            root = Path(directory)
            root.chmod(0o700)
            for name, encoded in artifacts.items():
                relative = PurePosixPath(name)
                if (not name or relative.is_absolute() or '..' in relative.parts
                        or '\\' in name or relative.as_posix() != name or name == '.'):
                    raise ValueError('invalid path')
                payload = base64.b64decode(encoded, validate=True)
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                path.chmod(0o600)
            assessment = assess(bundle['register'], root, now)
        report['gates'] = {name: {
            'evidence_complete': gate['evidence_complete'],
            'missing_requirement_count': len(gate['missing_requirements']),
            'gap_count': len(gate['gaps'])}
            for name, gate in assessment['gates'].items()}
        eligible = assessment['all_evidence_complete']
        report['status'] = 'EVIDENCE_COMPLETE' if eligible else 'EVIDENCE_INCOMPLETE'
        return report, 0 if eligible else 1
    except (ValueError, TypeError, KeyError, OSError, AttributeError, OverflowError):
        return report, 1


def main():
    event = os.getenv('GITHUB_EVENT_NAME', 'workflow_dispatch')
    if event == 'schedule':
        cadence = CADENCES.get(os.getenv('ASSURANCE_CRON', ''))
    elif event == 'workflow_dispatch':
        cadence = 'manual'
    else:
        cadence = None
    # Unknown triggers fail without reading private evidence.
    if cadence is None:
        report, code = {'status': 'UNSUPPORTED_TRIGGER', 'execution_authorized': False}, 1
    else:
        raw = os.getenv('ASSURANCE_EVIDENCE_BUNDLE_JSON', '')
        # Use an imported offline bundle only when no private bundle is supplied.
        if not raw and os.getenv('ASSURANCE_EVIDENCE_BUNDLE_FILE'):
            try:
                raw = Path(os.environ['ASSURANCE_EVIDENCE_BUNDLE_FILE']).read_text(encoding='utf-8')
            except OSError:
                raw = ' '  # Configured but unreadable: fail as invalid, never skip.
        if not raw:
            report = {'cadence': cadence, 'status': 'SKIPPED_NOT_CONFIGURED',
                      'execution_authorized': False, 'certification_issued': False}
            code = 0
        else:
            report, code = check_bundle(raw, cadence, datetime.now(timezone.utc))
    print(json.dumps(report, sort_keys=True))
    if report['status'] == 'SKIPPED_NOT_CONFIGURED':
        print('::notice::Evidence assessment skipped because ASSURANCE_EVIDENCE_BUNDLE_JSON is empty.')
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as stream:
            stream.write('## Scheduled evidence gates\n\n')
            stream.write('```json\n' + json.dumps(report, indent=2) + '\n```\n\n')
            stream.write('Evidence completeness only. No orders, suitability determination or certification.\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
