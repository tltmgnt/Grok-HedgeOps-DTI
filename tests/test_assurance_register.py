from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import tempfile
import unittest
from assurance_register import REQUIRED, assess, digest, template

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


class AssuranceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'artifact.txt').write_text('synthetic evidence')
        self.register = template()
        self.register['strategy_version'] = 'v1'
        for name, gate in self.register['gates'].items():
            gate.update(owner='operator', scope='synthetic test', subject_id=name,
                        criteria_version='v1')
            gate['evidence'] = [{'requirement': key, 'strategy_version': 'v1',
                'subject_id': name, 'observed_at': '2026-11-01T00:00:00Z',
                'expires_at': '2026-12-01T00:00:00Z', 'path': 'artifact.txt',
                'sha256': hashlib.sha256((self.root / 'artifact.txt').read_bytes()).hexdigest()}
                for key in REQUIRED[name]]
            self.review(gate)

    def review(self, gate):
        packet = {'strategy_version': 'v1', **{k: v for k, v in gate.items() if k != 'review'}}
        gate['review'] = {'decision': 'APPROVE_FOR_REVIEW', 'reviewer': 'reviewer',
            'rationale': 'Synthetic test only', 'packet_sha256': digest(packet),
            'reviewed_at': '2026-11-02T00:00:00Z', 'expires_at': '2026-12-01T00:00:00Z'}

    def report(self):
        return assess(self.register, self.root, NOW)

    def test_complete_is_review_only(self):
        result = self.report()
        self.assertTrue(result['all_eligible_for_human_review'])
        self.assertFalse(result['execution_authorized'])
        self.assertFalse(result['certification_issued'])

    def test_gates_independent(self):
        self.register['gates']['investor_fit']['evidence'] = []
        result = self.report()['gates']
        self.assertFalse(result['investor_fit']['eligible_for_human_review'])
        self.assertTrue(result['trading_evidence']['eligible_for_human_review'])

    def test_tamper_invalidates_every_gate(self):
        (self.root / 'artifact.txt').write_text('changed')
        self.assertFalse(self.report()['all_eligible_for_human_review'])

    def test_faults_fail_closed(self):
        original = deepcopy(self.register)
        mutations = [lambda g: g.update(blockers=['unresolved']),
            lambda g: g['evidence'][0].update(expires_at='2026-11-08T00:00:00Z'),
            lambda g: g['evidence'][0].update(observed_at='2027-01-01T00:00:00Z'),
            lambda g: g['evidence'][0].update(path='../escape'),
            lambda g: g['evidence'][0].update(strategy_version='v2'),
            lambda g: g['evidence'][0].update(subject_id='other'),
            lambda g: g['review'].update(reviewer='operator'),
            lambda g: g['review'].update(expires_at='2026-11-08T00:00:00Z'),
            lambda g: g.update(scope='changed'),
            lambda g: g['evidence'].append(deepcopy(g['evidence'][0]))]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.register = deepcopy(original)
                mutate(self.register['gates']['trading_evidence'])
                self.assertFalse(self.report()['gates']['trading_evidence']['eligible_for_human_review'])

    def test_schema_and_naive_time(self):
        with self.assertRaises(ValueError):
            assess({}, self.root, NOW)
        with self.assertRaises(ValueError):
            assess(self.register, self.root, datetime(2026, 11, 9))

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as other:
            external = Path(other) / 'secret'
            external.write_text('synthetic evidence')
            (self.root / 'link').symlink_to(external)
            gate = self.register['gates']['investor_fit']
            gate['evidence'][0]['path'] = 'link'
            self.review(gate)
            self.assertFalse(self.report()['gates']['investor_fit']['eligible_for_human_review'])
