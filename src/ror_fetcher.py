# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests

__generated_with = "0.23.10"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/ror")
COUNTRY_CODES = ["NL", "AW", "CW", "SX", "BQ"]
BASE_URL = "https://api.ror.org/v2/organizations"


def _extract_org(item: dict) -> dict:
    """Extract a flat dict of 20 fields from a ROR API item."""
    names = item.get("names", [])
    name = next((n["value"] for n in names if "ror_display" in n.get("types", [])), "")
    acronym = next((n["value"] for n in names if "acronym" in n.get("types", [])), None)
    aliases = "|".join(n["value"] for n in names if "alias" in n.get("types", []))
    locations = item.get("locations", [])
    geo = locations[0].get("geonames_details", {}) if locations else {}
    geonames_id = locations[0].get("geonames_id") if locations else None
    links = item.get("links", [])
    website = next((lnk["value"] for lnk in links if lnk.get("type") == "website"), None)
    wikipedia = next((lnk["value"] for lnk in links if lnk.get("type") == "wikipedia"), None)
    ext = {e["type"]: e.get("preferred") for e in item.get("external_ids", [])}
    types = item.get("types", [])
    return {
        "ror_id_url": item["id"],
        "ror_id": item["id"].replace("https://ror.org/", ""),
        "name": name,
        "acronym": acronym,
        "aliases": aliases or None,
        "org_type": "|".join(types) if types else None,
        "status": item.get("status"),
        "established_year": item.get("established"),
        "country_code": geo.get("country_code"),
        "location_name": geo.get("name"),
        "lat": geo.get("lat"),
        "lng": geo.get("lng"),
        "geonames_id": geonames_id,
        "website_url": website,
        "wikipedia_url": wikipedia,
        "isni_id": ext.get("isni"),
        "wikidata_id": ext.get("wikidata"),
        "grid_id": ext.get("grid"),
        "fundref_id": ext.get("fundref"),
    }


def _fetch_country(cc: str, data_dir: Path) -> int:
    """Paginate through the ROR API for one country code and write JSON files."""
    page = 1
    total_fetched = 0
    while True:
        resp = requests.get(
            BASE_URL,
            # omit query param so results use stable default ordering (not relevance)
            params={"filter": f"country.country_code:{cc}", "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        out = data_dir / f"page_{cc}_{page:03d}.json"
        out.write_text(json.dumps(data))
        total_fetched += len(items)
        # ROR v2 returns total at top level as number_of_results (not inside meta)
        if total_fetched >= data.get("number_of_results", 0):
            break
        page += 1
        time.sleep(0.1)
    return total_fetched


def load_orgs() -> list[dict]:
    """Return a list of flat dicts (20 base columns) from cached ROR JSON pages.

    Reads all page_*.json files from DATA_DIR and deduplicates by ROR ID.
    """
    seen: set[str] = set()
    orgs: list[dict] = []
    for path in sorted(DATA_DIR.glob("page_*.json")):
        data = json.loads(path.read_text())
        for item in data.get("items", []):
            ror_id = item.get("id", "")
            if ror_id in seen:
                continue
            seen.add(ror_id)
            orgs.append(_extract_org(item))
    return orgs


def fetch(force_refresh: bool = False) -> dict:
    """Fetch ROR data for all NL kingdom country codes and cache to DATA_DIR.

    Returns a metadata dict with record_count, fetched_at, and source_url.
    Skips network calls if cached data exists and force_refresh is False.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    existing = list(DATA_DIR.glob("page_*.json"))
    if existing and not force_refresh and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return meta
    for f in DATA_DIR.glob("page_*.json"):
        f.unlink()
    total = 0
    for cc in COUNTRY_CODES:
        total += _fetch_country(cc, DATA_DIR)
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": total,
        "source_url": BASE_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def setup():
    # Imports — make marimo available for the interactive cell below
    import marimo as mo
    return (mo,)


@app.cell(hide_code=True)
def preview(mo):
    # ROR preview — fetch (or read from cache) and display a table of all NL-kingdom organisations
    import pandas as pd
    result = fetch()
    orgs = load_orgs()
    df = pd.DataFrame(orgs)
    mo.vstack([
        mo.md(f"## ROR Fetch\nFetched **{result['record_count']}** records · last updated {result['fetched_at']}"),
        mo.ui.table(df),
    ])
    return


if __name__ == "__main__":
    app.run()
