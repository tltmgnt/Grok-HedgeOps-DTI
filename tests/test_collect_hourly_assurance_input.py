"""Tests that hourly artifacts cannot authorize assurance or trading."""
import base64
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.collect_hourly_assurance_input import NoFreshRun, collect, import_artifact
from scheduled_assurance import check_bundle, main

SHA = 'a' * 40
REPO = 'tltmgnt/Grok-HedgeOps-DTI'
NOW = datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc)
RUN_ID = 43035635785

FILES = {
    'run-status.json': json.dumps({
        'status': 'PASS',
        'checks': {
            'RELEASE_OUTCOME': 'success',
            'SIMULATION_OUTCOME': 'success',
            'VALIDATION_OUTCOME': 'success'},
        'mode': 'OFFLINE_SYNTHETIC_ONLY',
        'broker_orders_submitted': 0,
        'live_integrations_verified': False,
    }).encode(),
    'validation.json': json.dumps({
        'status': 'PASS',
        'mode': 'OFFLINE_SYNTHETIC_ONLY',
        'broker_orders_submitted': 0,
    }).encode(),
    'simulation.json': b'{"synthetic": true}\n',
    'simulation.txt': b'synthetic offline only\n',
    'release-check.log': b'PASS: offline validation\n',
}


def fake_gh(*args):
    if args[0] == 'api' and '/artifacts?' not in args[1]:
        return json.dumps({'workflow_runs': [{
            'id': RUN_ID, 'status': 'completed', 'conclusion': 'success',
            'head_branch': 'main', 'head_sha': SHA, 'event': 'schedule',
            'updated_at': (NOW - timedelta(minutes=15)).isoformat()}]})
    if args[0] == 'api':
        return json.dumps({'artifacts': [{
            'name': f'hourly-offline-evidence-{RUN_ID}', 'expired': False,
            'size_in_bytes': 3600}]})
    if args[:2] == ('run', 'download'):
        root = Path(args[-1])
        for name, data in FILES.items():
            (root / name).write_bytes(data)
        return ''
    raise AssertionError(args)


class OfflineAssuranceIntakeTests(unittest.TestCase):
    def test_imported_evidence_remains_incomplete_and_unauthorized(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'import.json'
            with patch('scripts.collect_hourly_assurance_input.gh', side_effect=fake_gh):
                self.assertEqual(collect(REPO, SHA, NOW, out), RUN_ID)
            bundle = json.loads(out.read_text())
            self.assertEqual(len(bundle['artifacts']), 5)
            self.assertEqual(
                json.loads(base64.b64decode(bundle['artifacts']['offline/run-status.json']))['status'],
                'PASS')
            self.assertTrue(all(not gate['evidence'] for gate in
                                bundle['register']['gates'].values()))
            report, code = check_bundle(out.read_text(), 'ten-minute', NOW)
            self.assertEqual(code, 1)
            self.assertEqual(report['status'], 'EVIDENCE_INCOMPLETE')
            self.assertFalse(report['execution_authorized'])
            self.assertFalse(report['certification_issued'])

    def test_fails_on_stale_or_mismatched_run(self):
        for different_sha, age in [(True, 15), (False, 240)]:
            with self.subTest(different_sha=different_sha, age=age):
                def bad_gh(*args):
                    if args[0] == 'api':
                        return json.dumps({'workflow_runs': [{
                            'id': RUN_ID, 'status': 'completed', 'conclusion': 'success',
                            'head_branch': 'main', 'event': 'schedule',
                            'head_sha': 'b' * 40 if different_sha else SHA,
                            'updated_at': (NOW - timedelta(minutes=age)).isoformat()}]})
                    raise AssertionError(args)
                with tempfile.TemporaryDirectory() as directory:
                    with patch('scripts.collect_hourly_assurance_input.gh',
                               side_effect=bad_gh):
                        with self.assertRaises(NoFreshRun):
                            collect(REPO, SHA, NOW, Path(directory) / 'out.json')

    def test_same_run_import_checks_artifact_age_and_keeps_gates_incomplete(self):
        for age in (0, 95, 96, -1):
            with self.subTest(age=age), tempfile.TemporaryDirectory() as directory:
                def current_run_gh(*args):
                    if args[0] == 'api':
                        self.assertIn(f'/runs/{RUN_ID}/artifacts?', args[1])
                        response = json.loads(fake_gh(*args))
                        response['artifacts'][0]['created_at'] = (NOW - timedelta(minutes=age)).isoformat()
                        return json.dumps(response)
                    return fake_gh(*args)

                out = Path(directory) / 'import.json'
                with patch('scripts.collect_hourly_assurance_input.gh', side_effect=current_run_gh):
                    if age < 0 or age > 95:
                        with self.assertRaisesRegex(ValueError, 'stale'):
                            import_artifact(REPO, SHA, RUN_ID, out, now=NOW)
                        self.assertFalse(out.exists())
                    else:
                        import_artifact(REPO, SHA, RUN_ID, out, now=NOW)
                        report, code = check_bundle(out.read_text(), 'ten-minute', NOW)
                        self.assertEqual((code, report['status']), (1, 'EVIDENCE_INCOMPLETE'))
                        self.assertFalse(report['execution_authorized'])

    def test_fails_on_nonpassing_validation(self):
        bad = dict(FILES)
        bad['validation.json'] = json.dumps({
            'status': 'FAIL', 'mode': 'OFFLINE_SYNTHETIC_ONLY',
            'broker_orders_submitted': 0}).encode()
        def bad_download(*args):
            if args[:2] == ('run', 'download'):
                root = Path(args[-1])
                for name, data in bad.items():
                    (root / name).write_bytes(data)
                return ''
            return fake_gh(*args)
        with tempfile.TemporaryDirectory() as directory:
            with patch('scripts.collect_hourly_assurance_input.gh',
                       side_effect=bad_download):
                with self.assertRaises(ValueError):
                    collect(REPO, SHA, NOW, Path(directory) / 'out.json')

    def test_file_fallback_is_assessed_not_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bundle.json'
            path.write_text(json.dumps({
                'register': {'schema_version': 1, 'strategy_version': 'test',
                             'gates': {}},
                'artifacts': {}}))
            env = {
                'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'ASSURANCE_EVIDENCE_BUNDLE_JSON': '',
                'ASSURANCE_EVIDENCE_BUNDLE_FILE': str(path),
            }
            with patch.dict('os.environ', env, clear=True):
                with redirect_stdout(io.StringIO()) as output:
                    code = main()
            self.assertEqual(code, 1)
            self.assertNotIn('SKIPPED_NOT_CONFIGURED', output.getvalue())


if __name__ == '__main__':
    unittest.main()
