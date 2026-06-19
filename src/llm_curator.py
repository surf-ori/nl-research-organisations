# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "openai", "python-dotenv"]
# ///
import os
from pathlib import Path

import marimo as mo
import openai
from dotenv import load_dotenv

load_dotenv()

__generated_with = "0.13.0"
app = mo.App(width="wide")

FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "RedHatAI/gemma-4-31B-it-NVFP4",
    "claude-sonnet-4-6",
    "gpt-4o",
    "llama3",
]

CURATE_PROMPT = """You are a research data curator. The source URL below lists member organisations.
Your task: return an updated CSV with columns `ror_id_url,name` (plus any extra columns present).
- Look up the source URL mentally and update the list based on your knowledge.
- Keep existing correct entries. Add missing ones. Remove entries no longer listed.
- Return ONLY the CSV content, no explanation, no markdown fences.

Source URL: {source_url}

Current CSV:
{current_csv}"""


def fetch_models(base_url: str, api_key: str) -> list[str]:
    try:
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        models = client.models.list()
        return [m.id for m in models.data]
    except Exception:
        return FALLBACK_MODELS


def test_connection(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    try:
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with just: ok"}],
            max_tokens=5,
        )
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)


def curate_csv(source_url: str, current_csv: str, base_url: str, api_key: str, model: str) -> str:
    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    prompt = CURATE_PROMPT.format(source_url=source_url, current_csv=current_csv)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md("## LLM Curator\nConfigure in the main notebook's LLM Configuration tab.")
    return


if __name__ == "__main__":
    app.run()
