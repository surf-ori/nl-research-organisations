# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "python-dotenv"]
# ///
"""
EU PIC ID Fetcher — PLACEHOLDER

Target API: EU Funding & Tenders Participant Portal
  Portal:    https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/participant-register
  API docs:  https://webgate.ec.europa.eu/funding-tenders-opportunities/display/OM/Webservices
  Guide:     https://eufunds.me/how-to-find-the-pic-number-of-an-organization/

When API access is available:
  1. Set EU_PIC_API_KEY in .env
  2. Implement _fetch_one(ror_url, name) -> str | None
  3. Cache results to data/raw/pic/<ror_id>.json
  4. Remove the NOT_IMPLEMENTED banner below

Required .env key: EU_PIC_API_KEY
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo

__generated_with = "0.23.10"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/pic")
NOT_IMPLEMENTED = True


def load_results() -> dict[str, str | None]:
    return {}


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": 0,
        "source_url": "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
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
    # EU PIC status — placeholder notice until API access is available
    mo.callout(
        mo.md("**PIC ID fetcher — not yet implemented.** Awaiting API access. See `src/pic_fetcher.py` for implementation notes."),
        kind="warn",
    )
    return


if __name__ == "__main__":
    app.run()
