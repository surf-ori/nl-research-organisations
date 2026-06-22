# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests
from dotenv import load_dotenv

load_dotenv()

__generated_with = "0.23.10"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/openalex")
API_URL = "https://api.openalex.org/institutions"
API_KEY = os.getenv("OPENALEX_API_KEY", "")
MAILTO = os.getenv("OPENALEX_MAILTO", "")
# 10 workers without API key (~10 req/s), 20 with key (~100 req/s allowed)
MAX_WORKERS = 20 if API_KEY else 10


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


def _fetch_one(ror_url: str) -> str:
    """Fetch and cache one ROR URL; returns the URL for progress tracking."""
    headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    params = {"filter": f"ror:{ror_url}", "mailto": MAILTO}
    resp = requests.get(API_URL, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    # Atomic write — avoids corruption if two processes/threads race on the same path
    dest = _cache_path(ror_url)
    with tempfile.NamedTemporaryFile("w", dir=dest.parent, delete=False, suffix=".tmp") as f:
        f.write(resp.text)
        tmp = f.name
    os.replace(tmp, dest)
    return ror_url


def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    uncached = [u for u in ror_urls if not _cache_path(u).exists() or force_refresh]
    if uncached:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, u): u for u in uncached}
            for future in as_completed(futures):
                future.result()  # re-raise any exception
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": filled,
        "source_url": API_URL,
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def setup():
    # Imports — make marimo available for the interactive cell below
    import marimo as mo
    return (mo,)


@app.cell(hide_code=True)
def summary(mo):
    # OpenAlex summary — show how many ROR organisations have a matching OpenAlex institution ID
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    mo.md(f"## OpenAlex\n**{filled}** institutions matched out of {len(results)} looked up")
    return


if __name__ == "__main__":
    app.run()
