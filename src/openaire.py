# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="full")


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
    DATA_DIR = Path("data/raw/openaire")
    TOKEN_URL = "https://aai.openaire.eu/oidc/token"
    API_URL = "https://api.openaire.eu/graph/v1/organizations"
    # Credentials from .env; auth is optional — the Graph API v1 is public without a token
    CLIENT_ID = os.getenv("OPENAIRE_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("OPENAIRE_CLIENT_SECRET", "")
    # More workers are safe when authenticated; the public endpoint is more restrictive
    MAX_WORKERS = 20 if (CLIENT_ID and CLIENT_SECRET) else 5

    def _get_token() -> str:
        """Obtain a Bearer token via client_credentials grant with HTTP Basic auth."""
        resp = requests.post(
            TOKEN_URL,
            data={"grant_type": "client_credentials", "scope": "openid"},
            auth=(CLIENT_ID, CLIENT_SECRET),  # Client Secret Basic per RFC 6749
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _cache_path(ror_url: str) -> Path:
        """Return the local JSON cache path for a given ROR URL."""
        short_id = ror_url.replace("https://ror.org/", "")
        return DATA_DIR / f"{short_id}.json"

    def _fetch_one(ror_url: str, headers: dict) -> str:
        """Fetch the OpenAIRE record for one ROR URL and write it to the cache atomically."""
        resp = requests.get(API_URL, params={"pid": ror_url}, headers=headers, timeout=15)
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
    """Read all cached OpenAIRE JSON files and return a mapping of ROR URL → OpenAIRE org ID.

    Returns None for any ROR URL whose organisation was not found in OpenAIRE.
    Handles both the `results[].id` and `content[].originalId` response shapes.
    """
    out: dict[str, str | None] = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        short_id = path.stem
        ror_url = f"https://ror.org/{short_id}"
        data = json.loads(path.read_text())
        results = data if isinstance(data, list) else data.get("results", data.get("content", []))
        out[ror_url] = (results[0].get("id") or results[0].get("originalId")) if results else None
    return out


@app.function
def load_identifiers() -> dict[str, dict[str, str | None]]:
    """Read all cached OpenAIRE JSON files and extract external identifiers from each
    organisation's `pids` array.

    Returns a mapping of ROR URL -> {column: value} for every recognised pid scheme
    (see _PID_SCHEME_COLUMNS). A handful of organisations carry more than one value for
    the same scheme (e.g. multiple historical PICs); the first one encountered is kept.
    Organisations not found in OpenAIRE map to a dict of all-None values.
    """
    # OpenAIRE's pid "scheme" names -> output column. Schemes vary in case in the wild
    # (e.g. "Wikidata" vs "wikidata"), so lookup is done case-insensitively.
    _PID_SCHEME_COLUMNS = {
        "pic":      "pic_id",
        "grid":     "grid_id",
        "wikidata": "wikidata_id",
        "isni":     "isni_id",
        "viaf":     "viaf_id",
        "ringgold": "ringgold_id",
        "fundref":  "fundref_id",
        "orgref":   "orgref_id",
        "orgreg":   "orgreg_id",
        "rrid":     "rrid_id",
        "linkedin": "linkedin_url",
        "mag_id":   "mag_id",
    }
    columns = set(_PID_SCHEME_COLUMNS.values())
    out: dict[str, dict[str, str | None]] = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        short_id = path.stem
        ror_url = f"https://ror.org/{short_id}"
        data = json.loads(path.read_text())
        results = data if isinstance(data, list) else data.get("results", data.get("content", []))
        row: dict[str, str | None] = dict.fromkeys(columns)
        if results:
            for pid in results[0].get("pids", []):
                column = _PID_SCHEME_COLUMNS.get(pid.get("scheme", "").lower())
                if column and row.get(column) is None:
                    row[column] = pid.get("value")
        out[ror_url] = row
    return out


@app.function
def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    """Fetch OpenAIRE organisation records for all given ROR URLs in parallel.

    Obtains a Bearer token if credentials are configured; falls back to public (unauth) access.
    Only downloads records that are not already cached (or all if force_refresh=True).
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    uncached = [u for u in ror_urls if not _cache_path(u).exists() or force_refresh]
    if uncached:
        # Auth is optional — Graph API v1 is publicly accessible without a token
        headers: dict = {}
        if CLIENT_ID and CLIENT_SECRET:
            try:
                token = _get_token()
                headers = {"Authorization": f"Bearer {token}"}
            except Exception as e:
                print(f"OpenAIRE token fetch failed ({e}), continuing without auth")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_fetch_one, u, headers): u for u in uncached}
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
    # Header — OpenAIRE module description and data source overview
    mo.md("""
    ## OpenAIRE — Organisation IDs

    Matches each ROR organisation against the
    [OpenAIRE Graph API](https://api.openaire.eu/graph/v1/organizations) to
    retrieve the canonical `openaire_org_id`.

    Authentication via `client_credentials` grant (Client Secret Basic) is
    optional — the public API is used as a fallback. Credentials are
    loaded from `.env` (`OPENAIRE_CLIENT_ID`, `OPENAIRE_CLIENT_SECRET`).

    Results are cached per-ROR-ID in `data/raw/openaire/`.

    Each cached record's `pids` array also carries other external identifiers
    (PIC, GRID, Wikidata, ISNI, VIAF, RingGold, FundRef, OrgRef, OrgReg, RRID,
    LinkedIn, MAG) — `load_identifiers()` extracts these without any extra
    network calls, and the assembler uses them as a fallback wherever ROR
    itself doesn't already supply that identifier.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — count of matched vs. looked-up organisations
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
