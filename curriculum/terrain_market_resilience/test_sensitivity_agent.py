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
                agent, "HTTPSConnection") as connect:
            connection = connect.return_value
            reply = io.BytesIO(json.dumps(response).encode())
            reply.status = 200
            connection.getresponse.return_value = reply
            self.assertEqual(agent.model_choice({"fixture": "terrain"}, "example"), "adjacency")
            connect.assert_called_once_with("api.openai.com", timeout=60)
            self.assertEqual(connection.request.call_args.args, ("POST", "/v1/responses"))
            request = json.loads(connection.request.call_args.kwargs["body"])
            self.assertFalse(request["store"])
            self.assertEqual(request["model"], "example")
            connection.close.assert_called_once()

    def test_planner_rejects_redirect(self):
        with patch.dict("os.environ", OPENAI_API_KEY="test"), patch.object(
                agent, "HTTPSConnection") as connect:
            connection = connect.return_value
            connection.getresponse.return_value.status = 307
            with self.assertRaisesRegex(ValueError, "HTTP 307"):
                agent.model_choice({}, "example")
            connection.request.assert_called_once()
            connection.close.assert_called_once()
