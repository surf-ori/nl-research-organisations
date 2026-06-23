# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "openai", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")

with app.setup:
    # Setup — imports, environment loading, and prompt constants
    import marimo as mo
    import os
    from pathlib import Path

    import openai
    from dotenv import load_dotenv
    load_dotenv()

    # Fallback model list when the API connection fails or returns no models
    FALLBACK_MODELS = [
        "openai/gpt-oss-120b",
        "RedHatAI/gemma-4-31B-it-NVFP4",
        "claude-sonnet-4-6",
        "gpt-4o",
        "llama3",
    ]

    # System prompt sent to the LLM for each curation request.
    # Uses concatenated string literals (not triple-quoted) so marimo's
    # textwrap.dedent() can correctly strip the 4-space indent from the block.
    CURATE_PROMPT = (
        "You are a research data curator. The source URL below lists member organisations.\n"
        "Your task: return an updated CSV with columns `ror_id_url,name` (plus any extra columns present).\n"
        "- Look up the source URL mentally and update the list based on your knowledge.\n"
        "- Keep existing correct entries. Add missing ones. Remove entries no longer listed.\n"
        "- Return ONLY the CSV content, no explanation, no markdown fences.\n"
        "\n"
        "Source URL: {source_url}\n"
        "\n"
        "Current CSV:\n"
        "{current_csv}"
    )


@app.function
def fetch_models(base_url: str, api_key: str) -> list[str]:
    """Return the list of model IDs available at the given OpenAI-compatible endpoint.

    Falls back to FALLBACK_MODELS if the connection fails or returns no models.
    """
    try:
        client = openai.OpenAI(base_url=base_url, api_key=api_key)
        models = client.models.list()
        return [m.id for m in models.data] or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


@app.function
def test_connection(base_url: str, api_key: str, model: str) -> tuple[bool, str]:
    """Send a minimal chat completion to verify that the endpoint and model are reachable.

    Returns (True, "Connection successful") on success, (False, error_message) on failure.
    """
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


@app.function
def curate_csv(source_url: str, current_csv: str, base_url: str, api_key: str, model: str) -> str:
    """Ask the LLM to update a membership CSV against its knowledge of the given source URL.

    The LLM receives the full CURATE_PROMPT template filled with source_url and current_csv.
    Returns the raw CSV text as returned by the model (no fences, no explanation).
    """
    client = openai.OpenAI(base_url=base_url, api_key=api_key)
    prompt = CURATE_PROMPT.format(source_url=source_url, current_csv=current_csv)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )
    return resp.choices[0].message.content.strip()


@app.cell(hide_code=True)
def header():
    # Header — LLM curator description and configuration pointer
    mo.md("""
    ## LLM Curator — AI-Assisted Membership Curation

    Provides three functions for LLM-based membership list curation:

    | Function | Purpose |
    |----------|---------|
    | `fetch_models(base_url, api_key)` | List available models at an OpenAI-compatible endpoint |
    | `test_connection(base_url, api_key, model)` | Verify endpoint reachability with a minimal request |
    | `curate_csv(source_url, current_csv, ...)` | Ask the LLM to update a membership CSV |

    Configure the endpoint and API key in the main notebook's **LLM Configuration** tab.
    """)
    return


@app.cell(hide_code=True)
def config_info():
    # Config info — show which environment variables are set for the LLM connection
    base_url = os.getenv("LLM_BASE_URL", "")
    api_key  = os.getenv("LLM_API_KEY", "")
    configured = bool(base_url and api_key)
    status_md = (
        "LLM environment: `LLM_BASE_URL` and `LLM_API_KEY` are **configured** via `.env`"
        if configured
        else "LLM environment: **not configured** — set `LLM_BASE_URL` and `LLM_API_KEY` in `.env`"
    )
    mo.callout(mo.md(status_md), kind="success" if configured else "warn")
    return


if __name__ == "__main__":
    app.run()
