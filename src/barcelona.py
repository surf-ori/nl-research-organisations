# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///

import marimo

__generated_with = "0.23.10"
app = marimo.App(width="wide")


with app.setup:
    # Setup — imports, constants, and internal helpers
    import marimo as mo
    import csv
    import difflib
    import json
    from datetime import datetime, timezone
    from pathlib import Path

    import requests

    # Cache directory, source URL, and fuzzy match threshold
    DATA_DIR        = Path("data/raw/barcelona")
    CSV_URL         = "https://barcelona-declaration.org/downloads/barcelonadeclaration_signatories_supporters.csv"
    FUZZY_THRESHOLD = 0.85

    def _read_signatories() -> list[dict]:
        """Read the cached CSV and return a list of normalised row dicts (lowercase stripped keys)."""
        rows = []
        # Compute path at call time so that patching DATA_DIR in tests takes effect
        with (DATA_DIR / "signatories.csv").open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k.strip().lower(): v.strip() for k, v in row.items()})
        return rows


@app.function
def load_results(ror_orgs: list[dict]) -> dict[str, bool]:
    """Match each ROR org against the cached Barcelona Declaration signatory list.

    First tries an exact ROR URL match; falls back to fuzzy name matching with
    a cutoff of FUZZY_THRESHOLD (0.85). Returns a mapping of ror_id_url → bool.
    """
    signatories  = _read_signatories()
    # Build a set of normalised ROR URLs from the CSV (for O(1) exact lookups)
    ror_ids_in_list = {
        row.get("ror_id", "").strip()
        for row in signatories
        if row.get("ror_id", "").strip()
    }
    names_in_list = [row.get("organisation_name", "") for row in signatories]
    results: dict[str, bool] = {}
    for org in ror_orgs:
        ror_url = org["ror_id_url"]
        if ror_url in ror_ids_in_list:
            results[ror_url] = True
            continue
        matches = difflib.get_close_matches(org["name"], names_in_list, n=1, cutoff=FUZZY_THRESHOLD)
        results[ror_url] = bool(matches)
    return results


@app.function
def fetch(force_refresh: bool = False) -> dict:
    """Download the Barcelona Declaration signatory CSV and cache it to DATA_DIR.

    Skips the download when the CSV already exists and force_refresh is False.
    Returns {"record_count": int, "fetched_at": str, "source_url": str}.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    csv_path  = DATA_DIR / "signatories.csv"
    if csv_path.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()
    csv_path.write_bytes(resp.content)
    rows = _read_signatories()
    meta = {
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "source_url":   CSV_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def header():
    # Header — Barcelona Declaration module description and matching strategy
    mo.md("""
    ## Barcelona Declaration — Open Research Information

    Downloads the list of
    [Barcelona Declaration](https://barcelona-declaration.org) signatories and
    matches each ROR organisation by:

    1. **Exact ROR ID match** — from the `ror_id` column in the CSV
    2. **Fuzzy name match** — `difflib.get_close_matches` with cutoff = 0.85

    Signatory CSV cached at `data/raw/barcelona/signatories.csv`.
    Call `fetch(force_refresh=True)` to re-download.
    """)
    return


@app.cell(hide_code=True)
def summary():
    # Summary — show the number of signatories in the cached CSV
    csv_exists = (DATA_DIR / "signatories.csv").exists()
    content = (
        mo.md(f"**{len(_read_signatories())} signatories** in the Barcelona Declaration CSV")
        if csv_exists
        else mo.callout(
            mo.md("No CSV cached yet — run `fetch()` or use the Pipeline Stages tab."),
            kind="warn",
        )
    )
    content
    return


if __name__ == "__main__":
    app.run()
