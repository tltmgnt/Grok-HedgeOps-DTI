import json
import os
import urllib.error
import urllib.request
from .models import AgentAssessment
from .validation import validate_bars


class GrokStrategicAgent:
    \"\"\"Optional xAI Chat Completions adapter. No request occurs until analyze().\"\"\"

    endpoint = "https://api.x.ai/v1/chat/completions"

    def __init__(self, api_key, model="grok-3-mini", timeout=20):
        if not api_key:
            raise ValueError("An xAI API key is required")
        self.api_key = api_key
        self.model = model
        self.timeout = int(timeout)

    @classmethod
    def from_env(cls):
        return cls(os.environ["XAI_API_KEY"],
                   os.getenv("XAI_MODEL", "grok-3-mini"))

    def analyze(self, bars, portfolio):
        closes = validate_bars(bars)
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content":
                 "You are a cautious strategy analyst. Return only JSON with keys "
                 "action (BUY, SELL, HOLD), confidence (0..1), summary, evidence (array), "
                 "risks (array). Do not claim certainty. This is decision support only."},
                {"role": "user", "content": json.dumps({
                    "closes": closes[-100:], "portfolio": portfolio
                })},
            ],
        }
        request = urllib.request.Request(
            self.endpoint, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode())
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            action = str(parsed.get("action", "HOLD")).upper()
            if action not in {"BUY", "SELL", "HOLD"}:
                raise ValueError("Invalid action from model")
            return AgentAssessment(
                "strategic_analyst", action,
                float(parsed.get("confidence", 0.0)),
                str(parsed.get("summary", "Grok strategic assessment")),
                list(parsed.get("evidence", [])),
                list(parsed.get("risks", [])),
                {"provider": "xAI", "model": self.model},
            )
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError,
                TypeError, json.JSONDecodeError):
            return AgentAssessment(
                "strategic_analyst", "HOLD", 0.0,
                "Grok request failed or returned invalid JSON; failed closed to HOLD.",
                [], ["Verify xAI connectivity, model identifier, and response format."],
                {"provider": "xAI", "model": self.model, "api_error": True},
            )
