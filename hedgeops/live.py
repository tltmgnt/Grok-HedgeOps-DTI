"""Live Grok adapter with bounded requests and safe operational logging."""
import json
import logging
import os
import time
from dotenv import load_dotenv
from openai import OpenAI, APIConnectionError, APITimeoutError, RateLimitError, APIStatusError

LOG = logging.getLogger("hedgeops.live")

class GrokServiceError(RuntimeError):
    pass

def create_grok_ask(client=None, model=None, timeout=30.0, max_retries=1,
                    max_requests=10):
    """Return a callable compatible with run_lab/create_case.

    Retries only transient connection/timeouts, rate limits and 5xx errors.
    The SDK's own retries are disabled to bound request attempts.
    """
    load_dotenv()
    model = model or os.getenv("XAI_MODEL")
    if not model or model == "replace_with_available_model_id":
        raise ValueError("Set XAI_MODEL to a model available in your xAI Console")
    if client is None:
        key = os.getenv("XAI_API_KEY")
        if not key or key == "replace_with_your_key":
            raise ValueError("Set XAI_API_KEY in .env")
        client = OpenAI(api_key=key, base_url="https://api.x.ai/v1",
                        timeout=timeout, max_retries=0)
    if type(max_retries) is not int or not 0 <= max_retries <= 3:
        raise ValueError("max_retries must be an integer from 0 to 3")

    if type(max_requests) is not int or not 1 <= max_requests <= 100:
        raise ValueError("max_requests must be an integer from 1 to 100")
    used = 0

    def ask(system, prompt):
        nonlocal used
        for attempt in range(max_retries + 1):
            if used >= max_requests:
                raise GrokServiceError("API request budget exhausted")
            used += 1
            started = time.monotonic()
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    timeout=timeout,
                )
                content = response.choices[0].message.content
                if not content:
                    raise GrokServiceError("Empty model response")
                try:
                    result = json.loads(content)
                except json.JSONDecodeError as exc:
                    raise GrokServiceError("Invalid JSON model response") from exc
                if not isinstance(result, dict):
                    raise GrokServiceError("Expected JSON object from model")
                LOG.info("grok_call_ok attempt=%d duration_ms=%d",
                         attempt + 1, int((time.monotonic() - started) * 1000))
                return result
            except (APIConnectionError, APITimeoutError, RateLimitError) as exc:
                transient = True
                error = exc
            except APIStatusError as exc:
                transient = exc.status_code >= 500
                error = exc
            if not transient or attempt == max_retries:
                LOG.warning("grok_call_failed attempts=%d type=%s",
                            attempt + 1, type(error).__name__)
                raise GrokServiceError(
                    f"Grok request failed ({type(error).__name__}); "
                    "check API access, model, quotas and network"
                ) from error
            # bounded backoff; no prompt, credentials or response body in logs
            time.sleep(min(2 ** attempt, 2))
        raise AssertionError("Unreachable")

    return ask
