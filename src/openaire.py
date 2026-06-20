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

DATA_DIR = Path("data/raw/openaire")
TOKEN_URL = "https://aai.openaire.eu/oidc/token"
API_URL = "https://api.openaire.eu/graph/v1/organizations"
CLIENT_ID = os.getenv("OPENAIRE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("OPENAIRE_CLIENT_SECRET", "")


def _get_token() -> str:
    """Obtain a Bearer token via client_credentials grant with HTTP Basic auth."""
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "client_credentials", "scope": "openid"},
        auth=(CLIENT_ID, CLIENT_SECRET),  # Client Secret Basic
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


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
        results = data if isinstance(data, list) else data.get("results", data.get("content", []))
        out[ror_url] = (results[0].get("id") or results[0].get("originalId")) if results else None
    return out


def fetch(ror_urls: list[str], force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    uncached = [u for u in ror_urls if not _cache_path(u).exists() or force_refresh]
    if uncached:
        # Auth is optional — Graph API v1 is publicly accessible without a token.
        # Use a Bearer token only if OPENAIRE_REFRESH_TOKEN is configured.
        headers = {}
        if CLIENT_ID and CLIENT_SECRET:
            try:
                token = _get_token()
                headers = {"Authorization": f"Bearer {token}"}
            except Exception as e:
                print(f"OpenAIRE token fetch failed ({e}), continuing without auth")
        for ror_url in uncached:
            resp = requests.get(
                API_URL,
                params={"pid": ror_url},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            _cache_path(ror_url).write_text(resp.text)
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
    mo.md(f"## OpenAIRE\n**{filled}** organisations matched out of {len(results)} looked up")
    return


if __name__ == "__main__":
    app.run()
