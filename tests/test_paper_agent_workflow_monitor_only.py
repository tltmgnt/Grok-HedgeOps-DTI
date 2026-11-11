"""Regression guard: the scheduled Paper Research Agent must never submit orders.

This checks the GitHub Actions job configuration, not brokerage availability.
"""
from pathlib import Path
import unittest

import yaml


WORKFLOW = (Path(__file__).resolve().parents[1] /
            ".github/workflows/paper-opportunity-intelligence.yml")


class PaperAgentReadOnlyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.raw = WORKFLOW.read_text(encoding="utf-8")
        self.workflow = yaml.safe_load(self.raw)
        self.steps = self.workflow["jobs"]["paper-session"]["steps"]

    def test_every_trigger_uses_only_monitor_only_entrypoint(self):
        commands = "\n".join(str(s.get("run", "")) for s in self.steps)
        self.assertEqual(commands.count("python paper_research_agent.py"), 1)
        self.assertIn("python paper_research_agent.py --monitor-only", commands)
        self.assertNotIn("python paper_research_agent.py\n", commands)
        self.assertNotIn("MONITOR_ONLY:", self.raw)
        self.assertIn("workflow_dispatch: {}", self.raw)
        self.assertIn("schedule:", self.raw)

    def test_paper_keys_and_kill_switch_are_unconditionally_safe(self):
        step = next(s for s in self.steps if
                    s.get("name") == "Run paper research agent (read-only)")
        env = step["env"]
        self.assertEqual(env["PAPER_AUTO_TRADING_ENABLED"], "false")
        self.assertEqual(env["PAPER_AUTO_KILL_SWITCH"], "true")
        self.assertEqual(env["ALPACA_API_KEY"],
                         "${{ secrets.ALPACA_PAPER_API_KEY }}")
        self.assertEqual(env["ALPACA_API_SECRET"],
                         "${{ secrets.ALPACA_PAPER_API_SECRET }}")
        self.assertNotIn("secrets.ALPACA_API_KEY", self.raw)
        self.assertNotIn("secrets.ALPACA_API_SECRET", self.raw)
        self.assertIn("exit 1", step["run"])


if __name__ == "__main__":
    unittest.main()
