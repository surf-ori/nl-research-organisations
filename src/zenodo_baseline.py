# /// script
# requires-python = ">=3.11"
# dependencies = ["marimo", "requests", "openpyxl", "python-dotenv"]
# ///
import json
from datetime import datetime, timezone
from pathlib import Path

import marimo as mo
import openpyxl
import requests

__generated_with = "0.23.10"
app = mo.App(width="wide")

DATA_DIR = Path("data/raw/zenodo")
ZENODO_URL = "https://zenodo.org/records/18957154/files/nl-orgs-baseline.xlsx?download=1"


def XLSX_PATH():
    return DATA_DIR / "nl-orgs-baseline.xlsx"


def load_ror_ids() -> set[str]:
    wb = openpyxl.load_workbook(XLSX_PATH(), read_only=True)
    ws = wb.active
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    ror_col = next((i for i, h in enumerate(headers) if h and str(h).strip().upper() == "ROR"), None)
    if ror_col is None:
        return set()
    ids = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        val = row[ror_col]
        if val:
            val = str(val).strip()
            if not val.startswith("https://"):
                val = f"https://ror.org/{val}"
            ids.add(val)
    return ids


def fetch(force_refresh: bool = False) -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "_metadata.json"
    xlsx_path = XLSX_PATH()
    if xlsx_path.exists() and not force_refresh and meta_path.exists():
        return json.loads(meta_path.read_text())
    resp = requests.get(ZENODO_URL, timeout=60)
    resp.raise_for_status()
    xlsx_path.write_bytes(resp.content)
    ids = load_ror_ids()
    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(ids),
        "source_url": ZENODO_URL,
    }
    meta_path.write_text(json.dumps(meta))
    return meta


@app.cell(hide_code=True)
def setup():
    # Imports — make marimo available for the interactive cell below
    import marimo as mo
    return (mo,)


@app.cell(hide_code=True)
def summary(mo):
    # Zenodo baseline summary — fetch (or read from cache) and report the number of ROR IDs
    result = fetch()
    mo.md(f"## Zenodo Baseline\n**{result['record_count']}** ROR ids in baseline · {result['fetched_at']}")
    return


if __name__ == "__main__":
    app.run()
