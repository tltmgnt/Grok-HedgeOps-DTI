import io
import contextlib
import base64
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scheduled_assurance import CADENCES, check_bundle, main
from assurance_register import template, REQUIRED

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


class ScheduledAssuranceTests(unittest.TestCase):
    def bundle(self):
        register = template()
        register['strategy_version'] = 'test'
        return {'register': register, 'artifacts': {}}

    def test_missing_and_malformed_fail_without_disclosure(self):
        for raw in ('', 'private malformed investor data', '[]', 'x' * 48001):
            report, code = check_bundle(raw, 'daily', NOW)
            self.assertEqual(code, 1)
            self.assertNotIn('private', json.dumps(report))

    def test_incomplete_has_only_redacted_counts(self):
        bundle = self.bundle()
        bundle['register']['gates']['investor_fit']['owner'] = 'SENSITIVE_PERSON'
        result, code = check_bundle(json.dumps(bundle), 'monthly', NOW)
        self.assertEqual(code, 1)
        self.assertEqual(result['status'], 'EVIDENCE_INCOMPLETE')
        self.assertEqual(len(result['gates']), 3)
        self.assertNotIn('SENSITIVE_PERSON', json.dumps(result))
        self.assertNotIn('packet_sha256', json.dumps(result))

    def test_paths_and_invalid_base64_rejected(self):
        for path, content in [('../escape', 'eA=='), ('/absolute', 'eA=='),
                              ('a/../b', 'eA=='), ('a\\b', 'eA=='),
                              ('a//b', 'eA=='), ('valid', '!notbase64')]:
            with self.subTest(path=path):
                bundle = self.bundle()
                bundle['artifacts'] = {path: content}
                result, code = check_bundle(json.dumps(bundle), 'daily', NOW)
                self.assertEqual(code, 1)
                self.assertEqual(result['status'], 'INVALID_EVIDENCE')

    def test_all_crons_are_distinct_and_supported(self):
        self.assertEqual(set(CADENCES.values()), {'ten-minute', 'daily', 'monthly', 'quarterly'})
        workflow = Path('.github/workflows/scheduled-assurance.yml').read_text()
        for cron in CADENCES:
            self.assertIn("cron: '" + cron + "'", workflow)

    def test_unknown_trigger_fails_without_evidence_read(self):
        with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'schedule', 'ASSURANCE_CRON': 'unknown'}, clear=True):
            with patch('scheduled_assurance.check_bundle') as check:
                self.assertEqual(main(), 1)
                check.assert_not_called()

    def test_complete_private_bundle_passes_without_review(self):
        bundle = self.bundle()
        content = b'synthetic private evidence'
        bundle['artifacts'] = {'evidence.txt': base64.b64encode(content).decode()}
        for name, gate in bundle['register']['gates'].items():
            gate.update(owner='owner', scope='synthetic', subject_id=name, criteria_version='1')
            gate['evidence'] = [{'requirement': key, 'strategy_version': 'test',
                'subject_id': name, 'observed_at': '2026-11-01T00:00:00Z',
                'expires_at': '2026-12-01T00:00:00Z', 'path': 'evidence.txt',
                'sha256': hashlib.sha256(content).hexdigest()} for key in REQUIRED[name]]
        result, code = check_bundle(json.dumps(bundle), 'quarterly', NOW)
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'EVIDENCE_COMPLETE')
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['certification_issued'])
        self.assertNotIn('synthetic private evidence', json.dumps(result))

    def test_incomplete_main_reports_action_without_private_text(self):
        bundle = self.bundle()
        bundle['register']['gates']['investor_fit']['owner'] = 'PRIVATE_OWNER'
        output = io.StringIO()
        env = {
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'ASSURANCE_EVIDENCE_BUNDLE_JSON': json.dumps(bundle),
        }
        with patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn('::error::Private assurance evidence incomplete', output.getvalue())
        self.assertIn('Synthetic offline evidence alone cannot', output.getvalue())
        self.assertNotIn('PRIVATE_OWNER', output.getvalue())

    def test_schedule_skips_only_an_empty_bundle(self):
        env = {'GITHUB_EVENT_NAME': 'schedule', 'ASSURANCE_CRON': next(iter(CADENCES))}
        for raw, code, status in [('', 0, 'SKIPPED_NOT_CONFIGURED'), (' ', 1, 'INVALID_EVIDENCE')]:
            with self.subTest(raw=raw), patch.dict(os.environ, env, clear=True):
                os.environ['ASSURANCE_EVIDENCE_BUNDLE_JSON'] = raw
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(), code)
                report = json.loads(output.getvalue().splitlines()[0])
                self.assertEqual(report['status'], status)
                self.assertFalse(report['execution_authorized'])
                self.assertFalse(report['certification_issued'])
                self.assertNotIn('gates', report)

    def test_manual_dispatch_skips_missing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / 'summary.md'
            output = io.StringIO()
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_STEP_SUMMARY': str(summary)}, clear=True):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main(), 0)
            report = json.loads(output.getvalue().splitlines()[0])
            self.assertEqual(report['cadence'], 'manual')
            self.assertEqual(report['status'], 'SKIPPED_NOT_CONFIGURED')
            self.assertNotIn('gates', report)
            self.assertIn('SKIPPED_NOT_CONFIGURED', summary.read_text())
