"""Run HEDGE 302 with a configured xAI model."""
import json
import os
import sys
from dotenv import load_dotenv
from openai import OpenAI
from hedgeops.lab import run_lab, render


def main():
    load_dotenv()
    key = os.getenv("XAI_API_KEY")
    model = os.getenv("XAI_MODEL")
    if not key or key == "replace_with_your_key":
        raise ValueError("Configure XAI_API_KEY in .env")
    if not model or model == "replace_with_available_model_id":
        raise ValueError("Configure XAI_MODEL in .env")
    client = OpenAI(api_key=key, base_url="https://api.x.ai/v1", timeout=60.0)

    def ask(system: str, prompt: str) -> dict:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty model response")
        return json.loads(content)

    return run_lab(" ".join(sys.argv[1:]), ask)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: python lab.py "Describe the problem"')
    try:
        print(render(main()))
    except (ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"Error: {exc}")
