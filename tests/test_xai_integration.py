"""Offline integration contract tests for the xAI-compatible OpenAI SDK client.

No network access or real API credentials are used.
"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx2 as httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError

from agent import ARRAY_FIELDS, REQUIRED_FIELDS, analyze


def report_json():
    return json.dumps({
        key: [] if key in ARRAY_FIELDS else "UNKNOWN" for key in REQUIRED_FIELDS
    })


def fake_response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class XAIIntegrationContractTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "XAI_API_KEY": "offline-test-key",
            "XAI_MODEL": "offline-test-model",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.dotenv = patch("agent.load_dotenv")
        self.dotenv.start()
        self.addCleanup(self.dotenv.stop)

    @patch("agent.OpenAI")
    def test_sdk_client_and_request_contract(self, client_class):
        client_class.return_value.chat.completions.create.return_value = fake_response(report_json())
        result = analyze("Assess a hypothetical decision")
        self.assertEqual(result["observation"], "UNKNOWN")
        kwargs = client_class.call_args.kwargs
        self.assertEqual(kwargs["base_url"], "https://api.x.ai/v1")
        self.assertEqual(kwargs["api_key"], "offline-test-key")
        self.assertEqual(kwargs["timeout"], 30.0)
        self.assertEqual(kwargs["max_retries"], 2)
        request = client_class.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "offline-test-model")
        self.assertEqual(request["messages"][1]["content"], "Assess a hypothetical decision")
        self.assertEqual(request["temperature"], 0.2)

    @patch("agent.OpenAI")
    def test_empty_and_malformed_model_responses(self, client_class):
        create = client_class.return_value.chat.completions.create
        for content in (None, "", "{bad json", "[]", '{"observation": "partial"}'):
            with self.subTest(content=content):
                create.return_value = fake_response(content)
                with self.assertRaises(ValueError):
                    analyze("test")

    @patch("agent.OpenAI")
    def test_timeout_propagates_without_retry_loop(self, client_class):
        request = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
        client_class.return_value.chat.completions.create.side_effect = APITimeoutError(request)
        with self.assertRaises(APITimeoutError):
            analyze("test")
        self.assertEqual(client_class.return_value.chat.completions.create.call_count, 1)

    @patch("agent.OpenAI")
    def test_connection_error_propagates(self, client_class):
        request = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
        client_class.return_value.chat.completions.create.side_effect = APIConnectionError(request=request)
        with self.assertRaises(APIConnectionError):
            analyze("test")

    @patch("agent.OpenAI")
    def test_authentication_status_propagates(self, client_class):
        request = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
        response = httpx.Response(401, request=request)
        client_class.return_value.chat.completions.create.side_effect = APIStatusError(
            "Unauthorized", response=response, body=None,
        )
        with self.assertRaises(APIStatusError) as caught:
            analyze("test")
        self.assertEqual(caught.exception.status_code, 401)

    @patch("agent.OpenAI")
    def test_no_client_created_for_missing_credentials_or_input(self, client_class):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            analyze(" ")
        with patch.dict(os.environ, {"XAI_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "XAI_API_KEY"):
                analyze("test")
        with patch.dict(os.environ, {"XAI_MODEL": ""}):
            with self.assertRaisesRegex(ValueError, "XAI_MODEL"):
                analyze("test")
        client_class.assert_not_called()


if __name__ == "__main__":
    unittest.main()
