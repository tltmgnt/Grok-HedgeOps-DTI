"""Prevent paper workflow from silently falling back to generic broker secrets."""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/paper-trading.yml'


class PaperCredentialIsolationTests(unittest.TestCase):
    def test_paper_workflow_requires_dedicated_key(self):
        content = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('ALPACA_API_KEY: ${{ secrets.ALPACA_PAPER_API_KEY }}', content)
        self.assertIn('ALPACA_API_SECRET: ${{ secrets.ALPACA_PAPER_API_SECRET }}', content)
        self.assertNotIn('secrets.ALPACA_PAPER_API_KEY ||', content)
        self.assertNotIn('secrets.ALPACA_PAPER_API_SECRET ||', content)

    def test_paper_submission_uses_paper_only_entrypoint(self):
        content = WORKFLOW.read_text(encoding='utf-8')
        self.assertIn('--submit-paper', content)
        self.assertIn('--reconcile-only', content)
        self.assertNotIn('--mode live', content)


if __name__ == '__main__':
    unittest.main()
