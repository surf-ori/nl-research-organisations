# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests
from dotenv import load_dotenv

load_dotenv()

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/openalex")
API_URL = "https://api.openalex.org/institutions"
API_KEY = os.getenv("OPENALEX_API_KEY", "")
MAILTO = os.getenv("OPENALEX_MAILTO", "")


def _cache_path(ror_url: str) -> Path:
    short_id = ror_url.replace("https://ror.org/", "")
    return DATA_DIR / f"{short_id}.json"


def load_results() -> dict[str, str | None]:
    out = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        short_id = path.stem
        ror_url = f"https://ror.org/{short_id}"
        data = json.loads(path.read_text())
        results = data.get("results", [])
        out[ror_url] = results[0].get("id") if results else None
    return out


def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for ror_url in ror_urls:
        cache = _cache_path(ror_url)
        if cache.exists() and not force_refresh:
            continue
        headers = {}
        if API_KEY:
            headers["Authorization"] = f"Bearer {API_KEY}"
        params = {"filter": f"ror:{ror_url}", "mailto": MAILTO}
        resp = requests.get(API_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        cache.write_text(resp.text)
        fetched += 1
        time.sleep(0.15)
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": filled,
        "source_url": API_URL,
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    mo.md(f"## OpenAlex\n**{filled}** institutions matched out of {len(results)} looked up")
    return


if __name__ == "__main__":
    app.run()
