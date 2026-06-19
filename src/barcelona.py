# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "python-dotenv"]
# ///
import csv
import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import requests

__generated_with = "0.13.0"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/barcelona")
CSV_URL = "https://barcelona-declaration.org/downloads/barcelonadeclaration_signatories_supporters.csv"
CSV_PATH = DATA_DIR / "signatories.csv"
FUZZY_THRESHOLD = 0.85


def _get_csv_path() -> Path:
    return DATA_DIR / "signatories.csv"


def _read_signatories() -> list[dict]:
    rows = []
    csv_path = _get_csv_path()
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k.strip().lower(): v.strip() for k, v in row.items()})
    return rows


def load_results(ror_orgs: list[dict]) -> dict[str, bool]:
    signatories = _read_signatories()
    ror_ids_in_list = {
        row.get("ror_id", "").strip()
        for row in signatories
        if row.get("ror_id", "").strip()
    }
    names_in_list = [row.get("organisation_name", "") for row in signatories]
    results = {}
    for org in ror_orgs:
        ror_url = org["ror_id_url"]
        if ror_url in ror_ids_in_list:
            results[ror_url] = True
            continue
        matches = difflib.get_close_matches(org["name"], names_in_list, n=1, cutoff=FUZZY_THRESHOLD)
        results[ror_url] = bool(matches)
    return results


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    csv_path = _get_csv_path()
    if csv_path.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()
    csv_path.write_bytes(resp.content)
    rows = _read_signatories()
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(rows),
        "source_url": CSV_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    result = fetch()
    mo.md(f"## Barcelona Declaration\n**{result['record_count']}** signatories · {result['fetched_at']}")
    return


if __name__ == "__main__":
    app.run()
