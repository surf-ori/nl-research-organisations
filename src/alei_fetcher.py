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

Verified against the live API (2026-07): OpenKvK's `query` param does a text search,
not an exact-equals match, and Dutch legal entities are usually registered under a
formal name that differs from a research organisation's public/brand name (e.g. Vrije
Universiteit Amsterdam is legally "Stichting VU") — the same mismatch
src/duo_ho_mbo.py hit with DUO's official names. This tries the org's name and each
alias as separate queries, and only accepts a result if the returned company's
`handelsnaam` and the query substring-contain each other in some direction, to avoid
trusting the API's own relevance ranking on an otherwise-unrelated result.
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

    def _validated_matches(query: str, matches: list[dict]) -> list[dict]:
        """Keep only matches whose handelsnaam plausibly corresponds to the query.

        OpenKvK's query does a text search, not an exact match, so a query can return
        a result that only shares a word or two — accept a match only if the query
        and the result's name substring-contain each other in some direction.
        """
        q = query.strip().lower()
        out = []
        for m in matches:
            handelsnaam = (m.get("handelsnaam") or "").strip().lower()
            if not handelsnaam:
                continue
            if q in handelsnaam or handelsnaam in q:
                out.append(m)
        return out

    def _fetch_one(org: dict) -> str:
        """Search by the org's name, then each alias, and cache the first validated result."""
        candidates = [org["name"]] + (org.get("aliases") or "").split("|")
        matches: list[dict] = []
        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate:
                continue
            found = _validated_matches(candidate, _search_openkvk(candidate))
            if found:
                matches = found
                break
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
        uncached = [o for o in orgs if not _cache_path(o["ror_id_url"]).exists() or force_refresh]
        for org in uncached:
            # Per-org try/except: some organisation names trip up OpenKvK's query
            # parser (e.g. a name containing "/" gets a 400 "ongeldige vraag" —
            # invalid query), and one bad name must not abort every org after it.
            try:
                _fetch_one(org)
            except Exception as e:
                print(f"ALEI/KVK fetch failed for {org['name']!r} ({e})")

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
