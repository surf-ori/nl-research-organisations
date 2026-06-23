# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "python-dotenv"]
# ///
"""
ALEI / KVK / ISO 8000-116 IBRN Fetcher — PLACEHOLDER

Target API: KVK Open Data API or ekys.org EKYS Search
  KVK API docs:  https://developers.kvk.nl/documentation
  EKYS search:   https://ekys.org/ekys_search/search/
  Wikipedia:     https://en.wikipedia.org/wiki/Authoritative_Legal_Entity_Identifier

When API access is available:
  1. Set KVK_API_KEY in .env
  2. Implement _fetch_one(ror_url, name) -> str | None using the KVK API
  3. Loop over ror_urls in fetch(), cache results to data/raw/alei/<ror_id>.json
  4. Remove the NOT_IMPLEMENTED banner from the marimo cell below

Required .env key: KVK_API_KEY
"""

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")


with app.setup:
    # Setup — imports and placeholder constants
    import marimo as mo
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    # Cache directory; NOT_IMPLEMENTED blocks the real fetch until the API is wired up
    DATA_DIR        = Path("data/raw/alei")
    NOT_IMPLEMENTED = True


@app.function
def load_results() -> dict[str, str | None]:
    """Return an empty mapping — ALEI API not yet implemented."""
    return {}


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Write a placeholder metadata file and return zero-count metadata.

    Replace this body with real API calls once KVK_API_KEY is available.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": 0,
        "source_url":   "https://developers.kvk.nl/documentation",
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — ALEI fetcher description and implementation roadmap
    mo.md("""
    ## ALEI / KVK — Authoritative Legal Entity Identifier

    Intended to fetch the **Authoritative Legal Entity Identifier (ALEI)** /
    KVK number for each Dutch research organisation via the
    [KVK Open Data API](https://developers.kvk.nl/documentation).

    **Status: not yet implemented.** See the module docstring for the
    implementation roadmap. Set `KVK_API_KEY` in `.env` to enable.
    """)
    return


@app.cell(hide_code=True)
def status():
    # Status — placeholder callout until the KVK API integration is complete
    mo.callout(
        mo.md(
            "**ALEI / KVK ID fetcher — not yet implemented.** "
            "Awaiting API access. See `src/alei_fetcher.py` for implementation notes."
        ),
        kind="warn",
    )
    return


if __name__ == "__main__":
    app.run()
