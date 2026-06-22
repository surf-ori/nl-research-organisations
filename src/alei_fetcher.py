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
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo

__generated_with = "0.23.10"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/alei")
NOT_IMPLEMENTED = True


def load_results() -> dict[str, str | None]:
    return {}


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": 0,
        "source_url": "https://developers.kvk.nl/documentation",
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def setup():
    # Imports — make marimo available for the interactive cell below
    import marimo as mo
    return (mo,)


@app.cell(hide_code=True)
def status(mo):
    # ALEI / KVK status — placeholder notice until API access is available
    mo.callout(
        mo.md("**ALEI / KVK ID fetcher — not yet implemented.** Awaiting API access. See `src/alei_fetcher.py` for implementation notes."),
        kind="warn",
    )
    return


if __name__ == "__main__":
    app.run()
