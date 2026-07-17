# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
"""
EU PIC ID Fetcher

Target API: EU Funding & Tenders Participant Register
  Portal:    https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/participant-register
  API docs:  https://webgate.ec.europa.eu/funding-tenders-opportunities/display/OM/Webservices

Requires an EU Login account with Participant Register API access, granted via your
organisation's LEAR (Legal Entity Appointed Representative). See README.md's "API keys"
section for the full setup process and links.

Required .env keys: EU_LOGIN_CLIENT_ID, EU_LOGIN_CLIENT_SECRET

ponytail: this has never been run against the real API — the person implementing it
does not have EU Login credentials to test with. The token/search endpoints and
request shape follow the EU's own documented example as closely as possible, but the
docs themselves warn "exact endpoint names may change — check the API documentation
after logging in." Verify both URLs and the response shape against the live API the
first time real credentials are available, before trusting this module's output.
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

    DATA_DIR = Path("data/raw/pic")
    TOKEN_URL = "https://webgate.ec.europa.eu/cas/oauth2/token"
    SEARCH_URL = "https://ec.europa.eu/info/funding-tenders/opportunities/api/organisation/search"
    CLIENT_ID = os.getenv("EU_LOGIN_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("EU_LOGIN_CLIENT_SECRET", "")

    def _get_token() -> str:
        """Obtain a Bearer token via the client_credentials grant."""
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _cache_path(ror_url: str) -> Path:
        """Return the local JSON cache path for a given ROR URL."""
        short_id = ror_url.replace("https://ror.org/", "")
        return DATA_DIR / f"{short_id}.json"

    def _search_organisation(name: str, token: str) -> list[dict]:
        """Search the Participant Register by organisation name; returns raw matches."""
        resp = requests.get(
            SEARCH_URL,
            params={"name": name},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def _fetch_one(org: dict, token: str) -> str:
        """Search for one organisation by name and cache the raw response."""
        matches = _search_organisation(org["name"], token)
        dest = _cache_path(org["ror_id_url"])
        with tempfile.NamedTemporaryFile("w", dir=DATA_DIR, delete=False, suffix=".tmp") as f:
            json.dump(matches, f)
            tmp = f.name
        os.replace(tmp, dest)
        return org["ror_id_url"]


@app.function
def load_results() -> dict[str, str | None]:
    """Read all cached PIC search results and return a mapping of ROR URL → PIC.

    Takes the first match's "pic" value per organisation, if any were found.
    """
    out: dict[str, str | None] = {}
    for path in DATA_DIR.glob("*.json"):
        if path.name == "_metadata.json":
            continue
        ror_url = f"https://ror.org/{path.stem}"
        matches = json.loads(path.read_text())
        out[ror_url] = matches[0].get("pic") if matches else None
    return out


@app.function
def fetch(orgs: list[dict], force_refresh: bool = False) -> dict:
    """Search the EU Participant Register for each organisation's PIC.

    `orgs` must be dicts with at least "ror_id_url" and "name" (this API searches by
    name, not by ROR ID). Requires EU_LOGIN_CLIENT_ID/EU_LOGIN_CLIENT_SECRET in .env —
    without them this returns a zero-count result rather than raising, matching the
    other placeholder-style stages so Full Refresh doesn't fail outright.
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CLIENT_ID and CLIENT_SECRET:
        try:
            token = _get_token()
            uncached = [o for o in orgs if not _cache_path(o["ror_id_url"]).exists() or force_refresh]
            for org in uncached:
                _fetch_one(org, token)
        except Exception as e:
            print(f"EU PIC fetch failed ({e}) — check EU_LOGIN_CLIENT_ID/EU_LOGIN_CLIENT_SECRET")

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
    # Header — EU PIC fetcher description
    mo.md("""
    ## EU PIC — Participant Identification Code

    Searches the
    [EU Funding & Tenders Participant Register](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/how-to-participate/participant-register)
    by organisation name to retrieve each Dutch research organisation's **PIC**.

    Requires an EU Login account with Participant Register API access (via your
    organisation's LEAR). Credentials are loaded from `.env`
    (`EU_LOGIN_CLIENT_ID`, `EU_LOGIN_CLIENT_SECRET`) — see `README.md` for how to
    obtain them. Without credentials configured, this stage reports zero records
    rather than failing.

    Results are cached per-ROR-ID in `data/raw/pic/`. A PIC is also available as a
    fallback from OpenAIRE's cached data (see `src/openaire.py`) when this official
    source isn't configured or doesn't have a match.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — count of matched vs. looked-up organisations
    results = load_results()
    filled = sum(1 for v in results.values() if v)
    mo.md(f"**{filled} / {len(results)}** organisations matched to a PIC")
    return


if __name__ == "__main__":
    app.run()
