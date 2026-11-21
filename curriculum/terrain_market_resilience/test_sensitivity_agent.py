import copy
import unittest
from unittest.mock import patch
import sensitivity_agent as agent


class AgentTests(unittest.TestCase):
    def test_planners_and_observations(self):
        for name in agent.FIXTURES:
            for tool in agent.TOOLS:
                packet = agent.investigate(name, lambda context: tool)
                self.assertEqual(packet["follow_up"]["tool"], tool)
                self.assertEqual(packet["review_status"], "pending")
                self.assertTrue(packet["follow_up"]["observations"])
        packet = agent.investigate("terrain")
        self.assertEqual(packet["study"]["review_cells"], [[1, 1], [1, 3]])
        self.assertEqual(packet["planner"], "offline rule")

    def test_reject_unlisted_action(self):
        with self.assertRaises(ValueError):
            agent.investigate("terrain", lambda context: "execute")

    def test_refuse_corrupt_rank_before_planning(self):
        grid, start, end, _ = agent.fixture("terrain")
        report = copy.deepcopy(agent.investigate_omissions(grid, start, end))
        report["ranking"].pop()
        with patch.object(agent, "investigate_omissions", return_value=report):
            with self.assertRaisesRegex(ValueError, "ranking"):
                agent.investigate("terrain", lambda _: self.fail("unverified input"))

    def test_model_selection_contract(self):
        import io
        import json
        response = {"status": "completed", "output": [{"content": [{
            "type": "output_text", "text": '{"tool":"adjacency"}'}]}]}
        with patch.dict("os.environ", OPENAI_API_KEY="test"), patch.object(
                agent, "urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as call:
            self.assertEqual(agent.model_choice({"fixture": "terrain"}, "example"), "adjacency")
            request = json.loads(call.call_args.args[0].data)
            self.assertFalse(request["store"])
            self.assertEqual(request["model"], "example")
