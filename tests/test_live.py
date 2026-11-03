import json
import unittest
from types import SimpleNamespace
from hedgeops.live import create_grok_ask, GrokServiceError

class FakeCompletion:
    def __init__(self, content):
        self.content = content
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=self.content))])

class LiveTests(unittest.TestCase):
    def test_success_and_configuration(self):
        completion = FakeCompletion('{"hypothesis":"test"}')
        client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
        ask = create_grok_ask(client=client, model="test-model", max_retries=0)
        self.assertEqual(ask("system", "problem")["hypothesis"], "test")
        self.assertEqual(completion.calls[0]["model"], "test-model")
        self.assertEqual(completion.calls[0]["response_format"], {"type": "json_object"})

    def test_invalid_json_rejected(self):
        completion = FakeCompletion("not json")
        client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
        ask = create_grok_ask(client=client, model="test-model", max_retries=0)
        with self.assertRaises(GrokServiceError):
            ask("system", "problem")

    def test_nonobject_json_rejected(self):
        completion = FakeCompletion(json.dumps([1, 2]))
        client = SimpleNamespace(chat=SimpleNamespace(completions=completion))
        ask = create_grok_ask(client=client, model="test-model", max_retries=0)
        with self.assertRaises(GrokServiceError):
            ask("system", "problem")

    def test_invalid_retry_budget(self):
        client = SimpleNamespace()
        with self.assertRaises(ValueError):
            create_grok_ask(client=client, model="test-model", max_retries=5)

if __name__ == "__main__":
    unittest.main()
