# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")


with app.setup:
    # Setup — imports, environment, constants, and internal helpers
    import marimo as mo
    import json
    import os
    import tempfile
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import datetime, timezone
    from pathlib import Path

    import requests
    from dotenv import load_dotenv
    load_dotenv()

    # Cache directory and API constants
    DATA_DIR = Path("data/raw/openalex")
    API_URL = "https://api.openalex.org/institutions"
    API_KEY = os.getenv("OPENALEX_API_KEY", "")
    MAILTO = os.getenv("OPENALEX_MAILTO", "")
    # Polite pool: 10 concurrent workers without a key (~10 req/s), 20 with one (~100 req/s)
    MAX_WORKERS = 20 if API_KEY else 10

    def _cache_path(ror_url: str) -> Path:
        """Return the local JSON cache path for a given ROR URL."""
        short_id = ror_url.replace("https://ror.org/", "")
        return DATA_DIR / f"{short_id}.json"

    def _fetch_one(ror_url: str) -> str:
        """Fetch the OpenAlex record for one ROR URL and write it to the cache atomically."""
        headers = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
        params = {"filter": f"ror:{ror_url}", "mailto": MAILTO}
        resp = requests.get(API_URL, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        dest = _cache_path(ror_url)
        # Atomic write: write to a temp file then rename, preventing partial reads under concurrency
        with tempfile.NamedTemporaryFile("w", dir=dest.parent, delete=False, suffix=".tmp") as f:
            f.write(resp.text)
            tmp = f.name
        os.replace(tmp, dest)
        return ror_url


@app.function
def load_results() -> dict[str, str | None]:
    """Read all cached OpenAlex JSON files and return a mapping of ROR URL → OpenAlex institution ID.

    Returns None for any ROR URL whose institution was not found in OpenAlex.
    """
    out: dict[str, str | None] = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        short_id = path.stem
        ror_url = f"https://ror.org/{short_id}"
        data = json.loads(path.read_text())
        results = data.get("results", [])
        out[ror_url] = results[0].get("id") if results else None
    return out


@app.function
def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    """Fetch OpenAlex institution records for all given ROR URLs in parallel.

    Only downloads records that are not already cached (or all if force_refresh=True).
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Identify which records still need to be downloaded
    uncached = [u for u in ror_urls if not _cache_path(u).exists() or force_refresh]
    if uncached:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, u): u for u in uncached}
            for future in as_completed(futures):
                future.result()  # propagate any exception immediately
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": filled,
        "source_url":   API_URL,
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — OpenAlex module description and data source overview
    mo.md("""
    ## OpenAlex — Institution IDs

    Matches each ROR organisation against the
    [OpenAlex](https://openalex.org) institutions API to retrieve the
    canonical `openalex_institution_id`.

    Results are cached per-ROR-ID in `data/raw/openalex/`.
    Call `fetch(ror_urls, force_refresh=True)` to refresh from the API.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — count of matched vs. looked-up institutions
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    total = len(results)
    mo.md(
        f"**{filled} matched** out of {total} looked up "
        f"({round(filled / total * 100) if total else 0}% hit rate)"
    )
    return


if __name__ == "__main__":
    app.run()
