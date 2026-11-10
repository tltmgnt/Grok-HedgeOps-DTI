"""DTI Ω × HedgeOps Ω — minimal Grok-powered intelligence agent."""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

# Re-export the existing validator API for callers importing from agent.
from report_validation import ARRAY_FIELDS, REQUIRED_FIELDS, validate_report

SYSTEM_PROMPT = """You are the DTI Ω × HedgeOps Ω Intelligence Agent.
Analyze temporal constraints, capacity, opportunity, uncertainty, risk and gaps.
Distinguish evidence from assumptions and inferences. Never fabricate sources.
You are advisory only; do not execute consequential decisions.
Respond with ONLY a JSON object with keys:
observation, evidence, assumptions, current_state, desired_state,
gaps, dependencies, bottlenecks, options, risks, uncertainty,
recommendation, verification.
Use arrays for evidence, assumptions, gaps, dependencies, bottlenecks,
options, risks and verification. State UNKNOWN when evidence is missing.
For recommendations specify falsification conditions in verification.
"""





def analyze(problem: str) -> dict:
    if not isinstance(problem, str) or not problem.strip():
        raise ValueError("Problem must be non-empty text")
    load_dotenv()
    key = os.getenv("XAI_API_KEY")
    model = os.getenv("XAI_MODEL")
    if not key or key == "replace_with_your_key":
        raise ValueError("Set XAI_API_KEY in your .env file")
    if not model or model == "replace_with_available_model_id":
        raise ValueError("Set XAI_MODEL to a model available in your xAI Console")
    client = OpenAI(
        api_key=key, base_url="https://api.x.ai/v1",
        timeout=30.0, max_retries=2,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": problem},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Model returned an empty response")
    return validate_report(content)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: python agent.py "Describe the problem to analyze"')
    try:
        print(json.dumps(analyze(" ".join(sys.argv[1:])), indent=2, ensure_ascii=False))
    except ValueError as exc:
        sys.exit(f"Error: {exc}")
