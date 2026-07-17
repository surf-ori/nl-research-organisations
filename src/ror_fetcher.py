# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="full")


with app.setup:
    # Setup — imports, constants, and internal helpers
    import marimo as mo
    import json
    import time
    from datetime import datetime, timezone
    from pathlib import Path

    import requests

    # Cache directory and API constants for the ROR v2 API
    DATA_DIR = Path("data/raw/ror")
    COUNTRY_CODES = ["NL", "AW", "CW", "SX", "BQ"]  # Kingdom of the Netherlands territories
    BASE_URL = "https://api.ror.org/v2/organizations"

    def _extract_org(item: dict) -> dict:
        """Extract a flat 19-field dict from a single ROR v2 API item."""
        names = item.get("names", [])
        # Pick the ROR display name; fall back to the first name if absent
        name = next((n["value"] for n in names if "ror_display" in n.get("types", [])), "")
        acronym = next((n["value"] for n in names if "acronym" in n.get("types", [])), None)
        aliases = "|".join(n["value"] for n in names if "alias" in n.get("types", []))
        locations = item.get("locations", [])
        geo = locations[0].get("geonames_details", {}) if locations else {}
        geonames_id = locations[0].get("geonames_id") if locations else None
        links = item.get("links", [])
        website = next((lnk["value"] for lnk in links if lnk.get("type") == "website"), None)
        wikipedia = next((lnk["value"] for lnk in links if lnk.get("type") == "wikipedia"), None)
        # Collapse external IDs (ISNI, Wikidata, GRID, FundRef) into a flat dict
        ext = {e["type"]: e.get("preferred") for e in item.get("external_ids", [])}
        types = item.get("types", [])
        return {
            "ror_id_url":       item["id"],
            "ror_id":           item["id"].replace("https://ror.org/", ""),
            "name":             name,
            "acronym":          acronym,
            "aliases":          aliases or None,
            "org_type":         "|".join(types) if types else None,
            "status":           item.get("status"),
            "established_year": item.get("established"),
            "country_code":     geo.get("country_code"),
            "location_name":    geo.get("name"),
            "lat":              geo.get("lat"),
            "lng":              geo.get("lng"),
            "geonames_id":      geonames_id,
            "website_url":      website,
            "wikipedia_url":    wikipedia,
            "isni_id":          ext.get("isni"),
            "wikidata_id":      ext.get("wikidata"),
            "grid_id":          ext.get("grid"),
            "fundref_id":       ext.get("fundref"),
        }

    def _fetch_country(cc: str, data_dir: Path) -> int:
        """Paginate through the ROR API for one country code; write one JSON file per page."""
        page = 1
        total_fetched = 0
        while True:
            resp = requests.get(
                BASE_URL,
                # Omit the query param so results use stable default ordering (not relevance).
                # With query=*, Elasticsearch scoring causes non-deterministic page overlap.
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
            # ROR v2 reports the total at the top level; meta.total does not exist
            if total_fetched >= data.get("number_of_results", 0):
                break
            page += 1
            time.sleep(0.1)  # polite rate-limiting between pages
        return total_fetched


@app.function
def load_orgs() -> list[dict]:
    """Load all cached ROR JSON pages and return a deduplicated list of flat org dicts.

    Reads every page_*.json file from DATA_DIR and deduplicates by ROR ID.
    Returns an empty list if no data has been fetched yet.
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


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Fetch ROR data for all NL-kingdom country codes and cache pages to DATA_DIR.

    Skips the network if cached pages already exist and force_refresh is False.
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    # Return early from cache when data is fresh
    existing = list(DATA_DIR.glob("page_*.json"))
    if existing and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())
    # Wipe old pages before re-fetching to avoid stale data mixing in
    for f in DATA_DIR.glob("page_*.json"):
        f.unlink()
    total = 0
    for cc in COUNTRY_CODES:
        total += _fetch_country(cc, DATA_DIR)
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": total,
        "source_url":   BASE_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — ROR module description and data source overview
    mo.md("""
    ## ROR — Research Organisation Registry

    Fetches all research organisations registered in the
    [Research Organisation Registry (ROR)](https://ror.org) for the five
    country codes of the Kingdom of the Netherlands:
    **NL, AW, CW, SX, BQ**.

    Data is cached locally as paginated JSON files in `data/raw/ror/`.
    Call `fetch(force_refresh=True)` to refresh from the API.
    """)
    return


@app.cell(hide_code=True)
def preview():
    # Data preview — table of the first 20 cached organisations
    import pandas as pd
    orgs = load_orgs()
    content = (
        mo.ui.table(pd.DataFrame(orgs).head(20))
        if orgs
        else mo.callout(
            mo.md("No data cached yet — run `fetch()` or use the Pipeline Stages tab."),
            kind="warn",
        )
    )
    mo.vstack([
        mo.md(f"**{len(orgs)} organisations** in local cache"),
        content,
    ])
    return


if __name__ == "__main__":
    app.run()
