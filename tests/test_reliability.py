import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from hedgeops.store import EventStore
from hedgeops.live import create_grok_ask, GrokServiceError

class ReliabilityTests(unittest.TestCase):
    def test_stale_write_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "events.sqlite3")
            with EventStore(path) as first, EventStore(path) as second:
                first.append("case", "created", {}, expected_stream_events=0)
                with self.assertRaises(ValueError):
                    second.append("case", "created", {}, expected_stream_events=0)
                self.assertEqual(len(first.history("case")), 1)
                self.assertTrue(first.verify_chain())

    def test_budget_limits_requests(self):
        class Completion:
            def __init__(self):
                self.count = 0
            def create(self, **kwargs):
                self.count += 1
                return SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"ok":true}'))])
        completion = Completion()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
        ask = create_grok_ask(client=client, model="test", max_retries=0,
                              max_requests=1)
        self.assertTrue(ask("system", "problem")["ok"])
        with self.assertRaises(GrokServiceError):
            ask("system", "problem")
        self.assertEqual(completion.count, 1)

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            create_grok_ask(client=object(), model="test", max_requests=0)

if __name__ == "__main__":
    unittest.main()
