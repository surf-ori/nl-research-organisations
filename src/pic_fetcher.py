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
    DATA_DIR        = Path("data/raw/pic")
    NOT_IMPLEMENTED = True


@app.function
def load_results() -> dict[str, str | None]:
    """Return an empty mapping — EU PIC API not yet implemented."""
    return {}


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Write a placeholder metadata file and return zero-count metadata.

    Replace this body with real API calls once EU_PIC_API_KEY is available.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": 0,
        "source_url":   "https://ec.europa.eu/info/funding-tenders/opportunities/portal/",
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — EU PIC fetcher description and implementation roadmap
    mo.md("""
    ## EU PIC — Participant Identification Code

    Intended to fetch the **EU Participant Identification Code (PIC)** for each
    Dutch research organisation via the
    [EU Funding & Tenders portal API](https://webgate.ec.europa.eu/funding-tenders-opportunities/display/OM/Webservices).

    **Status: not yet implemented.** See the module docstring for the
    implementation roadmap. Set `EU_PIC_API_KEY` in `.env` to enable.
    """)
    return


@app.cell(hide_code=True)
def status():
    # Status — placeholder callout until the EU PIC API integration is complete
    mo.callout(
        mo.md(
            "**PIC ID fetcher — not yet implemented.** "
            "Awaiting API access. See `src/pic_fetcher.py` for implementation notes."
        ),
        kind="warn",
    )
    return


if __name__ == "__main__":
    app.run()
