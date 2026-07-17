# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
"""
ALEI / KVK Fetcher

Target API: overheid.io OpenKvK
  Docs: https://overheid.io/documentatie/openkvk
  ALEI format: https://en.wikipedia.org/wiki/Authoritative_Legal_Entity_Identifier

Searches the Dutch Chamber of Commerce (KVK) business register by organisation name
and converts the matched KVK number into ALEI format: "NL.KVK:<kvknummer>", following
the ALEI spec's <jurisdiction>.<register-type>:<local-number> pattern (its own
worked example is "US-DE.BER:3031657" for a Delaware Business Entity Register entry).

Requires a free overheid.io account. See README.md's "API keys" section for signup.

Required .env key: OVERHEID_IO_API_KEY

ponytail: this has never been run against the real API — the person implementing it
does not have an overheid.io API key to test with. Verify the response shape (in
particular which field of a multi-match result is the right one to pick) against the
live API the first time a real key is available.
"""

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="full")


with app.setup:
    # Setup — imports, environment, constants, and internal helpers
    import marimo as mo
    import json
    import os
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path

    import requests
    from dotenv import load_dotenv
    load_dotenv()

    DATA_DIR = Path("data/raw/alei")
    SEARCH_URL = "https://api.overheid.io/openkvk"
    API_KEY = os.getenv("OVERHEID_IO_API_KEY", "")

    def _cache_path(ror_url: str) -> Path:
        """Return the local JSON cache path for a given ROR URL."""
        short_id = ror_url.replace("https://ror.org/", "")
        return DATA_DIR / f"{short_id}.json"

    def _search_openkvk(name: str) -> list[dict]:
        """Search OpenKvK by organisation name; returns the raw "bedrijf" matches."""
        resp = requests.get(
            SEARCH_URL,
            params={"query": name},
            headers={"ovio-api-key": API_KEY, "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("_embedded", {}).get("bedrijf", [])

    def _fetch_one(org: dict) -> str:
        """Search for one organisation by name and cache the raw response."""
        matches = _search_openkvk(org["name"])
        dest = _cache_path(org["ror_id_url"])
        with tempfile.NamedTemporaryFile("w", dir=DATA_DIR, delete=False, suffix=".tmp") as f:
            json.dump(matches, f)
            tmp = f.name
        os.replace(tmp, dest)
        return org["ror_id_url"]


@app.function
def load_results() -> dict[str, str | None]:
    """Read all cached OpenKvK search results and return a mapping of ROR URL → ALEI.

    Takes the first match's "dossiernummer" (KVK number) per organisation, if any were
    found, formatted as "NL.KVK:<dossiernummer>".
    """
    out: dict[str, str | None] = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        ror_url = f"https://ror.org/{path.stem}"
        matches = json.loads(path.read_text())
        kvk_number = matches[0].get("dossiernummer") if matches else None
        out[ror_url] = f"NL.KVK:{kvk_number}" if kvk_number else None
    return out


@app.function
def fetch(orgs: list[dict], force_refresh: bool = False) -> dict:
    """Search overheid.io's OpenKvK for each organisation's KVK number.

    `orgs` must be dicts with at least "ror_id_url" and "name" (OpenKvK searches by
    name). Requires OVERHEID_IO_API_KEY in .env — without it this returns a zero-count
    result rather than raising, matching the other placeholder-style stages so Full
    Refresh doesn't fail outright.
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if API_KEY:
        try:
            uncached = [o for o in orgs if not _cache_path(o["ror_id_url"]).exists() or force_refresh]
            for org in uncached:
                _fetch_one(org)
        except Exception as e:
            print(f"ALEI/KVK fetch failed ({e}) — check OVERHEID_IO_API_KEY")

    results = load_results()
    filled = sum(1 for v in results.values() if v)
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": filled,
        "source_url":   SEARCH_URL,
    }
    (DATA_DIR / "_metadata.json").write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — ALEI fetcher description
    mo.md("""
    ## ALEI / KVK — Authoritative Legal Entity Identifier

    Searches [overheid.io's OpenKvK](https://overheid.io/documentatie/openkvk) by
    organisation name to retrieve each Dutch research organisation's KVK number,
    formatted as an [ALEI](https://en.wikipedia.org/wiki/Authoritative_Legal_Entity_Identifier)
    (`NL.KVK:<kvknummer>`).

    Requires a free overheid.io account. Credentials are loaded from `.env`
    (`OVERHEID_IO_API_KEY`) — see `README.md` for signup. Without a key configured,
    this stage reports zero records rather than failing.

    Results are cached per-ROR-ID in `data/raw/alei/`.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — count of matched vs. looked-up organisations
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    mo.md(f"**{filled} / {len(results)}** organisations matched to an ALEI")
    return


if __name__ == "__main__":
    app.run()
